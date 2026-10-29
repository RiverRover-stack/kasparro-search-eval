from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.analysis import execute_analysis
from backend.app.classification import ControlledStubClassifier
from backend.app.classification.adapters import LiteralAbsenceRouter
from backend.app.findings import ENGINE_NAMES, branded_outlier_engine, build_findings, literal_name_counts
from backend.app.importer import import_pack
from backend.app.models import (
    ModelAttemptRecord,
    ResponseClassificationRecord,
    ResponseRecord,
    ReportVersion,
)
from backend.app.reports import ReportServiceError, create_report, get_report
from backend.app.schemas import ReportContent, ReportRemedy
from tools.check_report_evidence import check_report_evidence

ROOT = Path(__file__).resolve().parents[1]
QUOTE_FAILURE = (
    "Groq HTTP 400: jsonschema: '/supporting_excerpts/1/quote' does not validate with enum"
)


@pytest.fixture
def run(session_factory: sessionmaker[Session]):
    """Rule for absent answers, stub 'model' for named answers; two named answers fail."""
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        named = [
            response.id
            for response in session.scalars(select(ResponseRecord).order_by(ResponseRecord.id))
            if "kasparro" in response.answer_text.casefold()
        ]
        failing = {response_id: QUOTE_FAILURE for response_id in named[:2]}
        router = LiteralAbsenceRouter(ControlledStubClassifier(failures=failing))
        analysis = execute_analysis(session, dataset.dataset_id, router, 20_000)
        report = create_report(session, analysis.analysis_id, "analyst", "request-create")
        yield SimpleNamespace(
            session=session, analysis=analysis, report=report, failing=set(failing), named=named
        )


def _texts(content: ReportContent) -> list[str]:
    return [
        value
        for item in [*content.diagnostics, *content.remedies]
        for value in item.model_dump().values()
        if isinstance(value, str)
    ]


def test_literal_block_counts_every_response_with_coverage(run) -> None:
    block = run.report.current_version.content.summary["literal_name_counts"]
    truth = {}
    for response in run.session.scalars(select(ResponseRecord)):
        cell = truth.setdefault(response.engine, [0, 0])
        cell[0] += "kasparro" in response.answer_text.casefold()
        cell[1] += 1
    assert block["total"]["responses"] == 150
    assert block["total"]["named"] + block["total"]["absent"] == 150
    for engine, (named, responses) in truth.items():
        cell = block["by_engine"][engine]
        assert (cell["named"], cell["responses"]) == (named, responses)
        assert {"successful", "failed", "skipped"} <= set(cell)
    assert set(block["by_prompt_branding"]) >= {"branded", "unbranded"}
    for cell in block["by_engine_and_branding"].values():
        assert cell["named"] + cell["absent"] == cell["responses"]
        assert cell["successful"] + cell["failed"] + cell["skipped"] == cell["responses"]
    # No unbranded prompt names the brand in the archived pack.
    assert block["by_prompt_branding"]["unbranded"]["named"] == 0


def test_model_block_is_separate_and_counts_only_non_rule_results(run) -> None:
    summary = run.report.current_version.content.summary
    model = summary["model_classification"]
    rule_ids = set(
        run.session.scalars(
            select(ModelAttemptRecord.response_id).where(ModelAttemptRecord.execution_mode == "rules")
        )
    )
    results = list(run.session.scalars(select(ResponseClassificationRecord)))
    valid = [r for r in results if r.status == "successful" and r.response_id not in rule_ids]
    assert model["calls"]["valid"] == len(valid)
    assert model["calls"]["failed"] == len(run.failing) == 2
    assert model["calls"]["quote_rejections"] == 2
    assert model["calls"]["valid"] + model["calls"]["failed"] == len(run.named) - model["calls"]["skipped"]
    assert model["mentioned_only"] + model["recommended"] == model["calls"]["valid"]
    assert model["negative"] == sum(r.classification["negative_characterization"] for r in valid)
    # Not blended: the literal block counts all 150; the model block only the model's answers.
    assert model["calls"]["valid"] < summary["literal_name_counts"]["total"]["responses"]
    assert set(summary) >= {"literal_name_counts", "model_classification"}
    joined = " ".join(model["notes"])
    assert f"{model['calls']['failed']} of {model['calls']['valid'] + model['calls']['failed']}" in joined
    assert "recommend" in joined


def test_exactly_three_diagnostics_and_remedies_with_problem(run) -> None:
    content = run.report.current_version.content
    assert len(content.diagnostics) == 3
    assert len(content.remedies) == 3
    for remedy in content.remedies:
        assert remedy.problem and remedy.problem.strip()
    for diagnostic in content.diagnostics:
        assert 2 <= len(diagnostic.evidence_response_ids) <= 3
        assert "hypothesis" in diagnostic.possible_explanation.lower()
        assert re.search(r"\d+ of \d+", diagnostic.observed_pattern)
    for diagnostic in content.diagnostics[:2]:
        assert re.search(r"\d+ successful, \d+ failed, \d+ skipped", diagnostic.observed_pattern)
    assert re.search(r"\d+ of \d+ model calls failed", content.diagnostics[2].observed_pattern)


def _keys(value) -> list[str]:
    if isinstance(value, dict):
        return [k for k, v in value.items()] + [k for v in value.values() for k in _keys(v)]
    if isinstance(value, list):
        return [k for v in value for k in _keys(v)]
    return []


def test_new_summary_has_no_blended_average_anywhere(run) -> None:
    summary = run.report.current_version.content.summary
    assert "average_visibility_score" not in _keys(summary)
    assert "average" not in json.dumps(summary).lower()
    assert set(summary) == {
        "execution_mode", "model_identifier", "prompt_version", "prompt_mapping_version",
        "score_scope", "literal_name_counts", "model_classification",
    }


def test_no_text_cites_the_blended_average(run) -> None:
    for text in _texts(run.report.current_version.content):
        # only the branded-prompt average (a comparison inside one group) may be named
        assert "average" not in text.lower().replace("branded-prompt average", "")
        assert "overall" not in text.lower() and "blended" not in text.lower()
        assert "visibility score" not in text.lower()
    assert "average" not in json.dumps(run.report.current_version.content.summary).lower()


def test_evidence_ids_belong_to_analysis_and_pass_the_checker(run) -> None:
    results = list(run.session.scalars(select(ResponseClassificationRecord)))
    by_response = {
        r.response_id: {"status": r.status, "classification": r.classification} for r in results
    }
    answers = {r.id: r.answer_text for r in run.session.scalars(select(ResponseRecord))}
    content = run.report.current_version.content
    for item in [*content.diagnostics, *content.remedies]:
        assert set(item.evidence_response_ids) <= set(by_response)
    assert check_report_evidence(content, by_response, answers) == []


def test_generation_is_deterministic(run, session_factory: sessionmaker[Session]) -> None:
    from backend.app.reports import _initial_content

    first = _initial_content(run.session, run.analysis.analysis_id)
    second = _initial_content(run.session, run.analysis.analysis_id)
    assert first.model_dump() == second.model_dump()


def _branded(cells: dict[str, tuple[int, int]]) -> dict:
    """Minimal literal block with only branded cells: {engine: (named, responses)}."""
    return {
        "by_engine_and_branding": {
            f"{engine}|branded": {"named": named, "responses": responses}
            for engine, (named, responses) in cells.items()
        },
        "by_prompt_branding": {
            "branded": {
                "named": sum(named for named, _ in cells.values()),
                "responses": sum(responses for _, responses in cells.values()),
            }
        },
    }


def test_branded_outlier_is_the_engine_furthest_from_the_branded_average() -> None:
    literal = _branded({"chatgpt": (25, 30), "gemini": (22, 30), "aimode": (25, 30)})
    assert branded_outlier_engine(literal) == "gemini"


def test_branded_outlier_ties_break_by_engine_order() -> None:
    literal = _branded({"aimode": (5, 10), "gemini": (5, 10), "chatgpt": (5, 10)})
    assert branded_outlier_engine(literal) == "chatgpt"


def test_diagnostics_are_one_per_kind_with_the_expected_ids(run) -> None:
    content = run.report.current_version.content
    assert [d.id for d in content.diagnostics] == [
        "unbranded-name-rate", "branded-engine-gap", "model-findings"
    ]
    literal = content.summary["literal_name_counts"]
    unbranded = literal["by_prompt_branding"]["unbranded"]
    first = content.diagnostics[0].observed_pattern
    assert f"{unbranded['named']} of {unbranded['responses']}" in first
    for engine, cell in literal["by_engine_and_branding"].items():
        if engine.endswith("|unbranded"):
            assert f"{cell['named']} of {cell['responses']}" in first
    outlier = branded_outlier_engine(literal)
    assert ENGINE_NAMES[outlier] in content.diagnostics[1].title
    cell = literal["by_engine_and_branding"][f"{outlier}|branded"]
    assert f"{cell['named']} of {cell['responses']}" in content.diagnostics[1].observed_pattern


def test_model_diagnostic_cites_only_model_classified_answers(run) -> None:
    rule_ids = set(
        run.session.scalars(
            select(ModelAttemptRecord.response_id).where(ModelAttemptRecord.execution_mode == "rules")
        )
    )
    model = run.report.current_version.content.diagnostics[2]
    assert model.evidence_response_ids
    assert not set(model.evidence_response_ids) & rule_ids
    assert "recommend" in model.possible_explanation
    assert "2 of" in model.observed_pattern  # the two failed calls, with their denominator


def _record(response_id, engine, prompt_id, status="successful", classification=None):
    return SimpleNamespace(
        response_id=response_id, engine=engine, prompt_id=prompt_id, status=status,
        reason=None, classification=classification,
    )


def test_unmapped_prompts_cannot_be_reported() -> None:
    records = [_record("a", "chatgpt", "p1")]
    with pytest.raises(ValueError, match="branded and unbranded"):
        build_findings(records, {"a": "text"}, {}, set(), "stub")


def test_no_model_classified_answers_cannot_be_reported() -> None:
    records = [_record("a", "chatgpt", "p1"), _record("b", "chatgpt", "p2")]
    labels = {"p1": "branded", "p2": "unbranded"}
    with pytest.raises(ValueError, match="model-classified"):
        build_findings(records, {"a": "no", "b": "no"}, labels, {"a", "b"}, "rules")


def test_all_unbranded_answers_naming_the_brand_still_gives_evidence() -> None:
    classification = {"recommended": False, "brand_mentioned": True, "negative_characterization": False}
    records = [
        _record("a", "chatgpt", "p1", classification=classification),
        _record("b", "chatgpt", "p2", classification=classification),
    ]
    labels = {"p1": "branded", "p2": "unbranded"}
    _, diagnostics, _ = build_findings(
        records, {"a": "Kasparro", "b": "Kasparro"}, labels, set(), "stub"
    )
    assert diagnostics[0].evidence_response_ids == ["b"]


def test_literal_name_counts_ignores_classification_failures() -> None:
    records = [
        SimpleNamespace(response_id="a", engine="chatgpt", prompt_id="p1", status="failed"),
        SimpleNamespace(response_id="b", engine="chatgpt", prompt_id="p2", status="skipped"),
    ]
    answers = {"a": "Kasparro is here", "b": "nothing"}
    block = literal_name_counts(records, answers, {"p1": "branded", "p2": "unbranded"})
    assert block["total"] == {
        "responses": 2, "named": 1, "absent": 1, "successful": 0, "failed": 1, "skipped": 1,
    }


def test_old_remedy_without_problem_still_validates_and_keeps_its_hash(run) -> None:
    version = run.session.scalar(select(ReportVersion))
    old = json.loads(json.dumps(version.content))
    for remedy in old["remedies"]:
        remedy.pop("problem")
    assert ReportRemedy.model_validate(old["remedies"][0]).problem is None
    version.content = old
    run.session.commit()
    stored_hash = version.content_hash
    view = get_report(run.session, run.report.report_id)
    assert view.current_version.content_hash == stored_hash
    assert all(remedy.problem is None for remedy in view.current_version.content.remedies)


def test_report_needs_results(session_factory: sessionmaker[Session]) -> None:
    from backend.app.models import AnalysisRun

    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        session.add(
            AnalysisRun(
                id="empty", dataset_id=dataset.dataset_id, status="completed",
                execution_mode="stub", model_identifier="m", prompt_version="v",
            )
        )
        session.commit()
        with pytest.raises(ReportServiceError) as caught:
            create_report(session, "empty", "analyst", "request-create")
        assert caught.value.code == "analysis_has_no_results"


def _scenario(unbranded_named=False, failed_reason=None, failures=1):
    """Tiny synthetic analysis: p1 branded, p2 unbranded; chatgpt, gemini, aimode answer each."""
    ok = {"recommended": False, "brand_mentioned": True, "negative_characterization": False}
    records, answers = [], {}
    for engine in ("aimode", "gemini", "chatgpt"):
        for prompt, text in (("p1", "Kasparro is here"), ("p2", "Kasparro" if unbranded_named else "nothing")):
            response_id = f"{engine}-{prompt}"
            answers[response_id] = text
            records.append(_record(response_id, engine, prompt, classification=ok))
    for record in records[:failures]:
        record.status, record.classification, record.reason = "failed", None, failed_reason
    return records, answers, {"p1": "branded", "p2": "unbranded"}


def test_unbranded_wording_follows_the_numbers() -> None:
    zero = build_findings(*_scenario(False), set(), "stub")
    some = build_findings(*_scenario(True), set(), "stub")
    assert "never named" in zero[1][0].title
    assert "never named" not in some[1][0].title and "never named" not in some[2][1].problem
    assert "never named" in zero[2][1].problem
    assert "6 answers" not in some[2][1].problem


def test_per_engine_split_uses_the_fixed_engine_order() -> None:
    _, diagnostics, _ = build_findings(*_scenario(), set(), "stub")
    text = diagnostics[0].observed_pattern
    assert text.index("ChatGPT") < text.index("Gemini") < text.index("Google AI Mode")


def test_engine_size_comes_from_the_data() -> None:
    _, diagnostics, _ = build_findings(*_scenario(), set(), "stub")
    assert "about 30" not in diagnostics[1].possible_explanation
    assert "1 branded answers" in diagnostics[1].possible_explanation


def test_quote_remedy_with_no_failures_says_so_and_cites_model_answers() -> None:
    _, _, remedies = build_findings(*_scenario(failures=0), set(), "stub")
    first = remedies[0]
    assert "0 of 6" in first.problem
    assert "re-run" not in first.validation_step.lower()
    assert "sentence numbers" not in first.action
    assert set(first.evidence_response_ids) <= {r for r in _scenario(failures=0)[1]}
    assert len(first.evidence_response_ids) >= 2


def test_quote_remedy_with_other_failures_does_not_blame_quotes() -> None:
    _, _, remedies = build_findings(*_scenario(failed_reason="Groq HTTP 429: busy"), set(), "stub")
    first = remedies[0]
    assert "0 of those failed because of a quote mismatch" in first.problem
    assert "sentence numbers" not in first.action


def test_quote_remedy_with_quote_failures_keeps_the_proposal() -> None:
    reason = "jsonschema: '/supporting_excerpts/1/quote' does not validate"
    _, _, remedies = build_findings(*_scenario(failed_reason=reason), set(), "stub")
    assert "sentence numbers" in remedies[0].action


def test_held_out_sentence_matches_the_frozen_evaluation() -> None:
    from backend.app.findings import model_classification

    records = [_record("a", "chatgpt", "p1", classification={
        "recommended": False, "brand_mentioned": True, "negative_characterization": False})]
    notes = " ".join(model_classification(records, set(), "hosted_groq")["notes"])
    assert "only 5 of 8" in notes and "0 recommendations" in notes
    assert "recall for recommendations was 0" not in notes
    assert "held-out" not in " ".join(model_classification(records, set(), "stub")["notes"])


def test_unmapped_dataset_gives_409_analysis_not_reportable(run, monkeypatch) -> None:
    from backend.app import reports

    monkeypatch.setattr(reports, "prompt_branding_labels", lambda source_run_id: (None, {}))
    with pytest.raises(ReportServiceError) as caught:
        reports._initial_content(run.session, run.analysis.analysis_id)
    assert (caught.value.status_code, caught.value.code) == (409, "analysis_not_reportable")


def test_plain_stub_analysis_is_reportable(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        analysis = execute_analysis(session, dataset.dataset_id, ControlledStubClassifier(), 20_000)
        assert create_report(session, analysis.analysis_id, "analyst", "r").current_version.content.diagnostics


QUOTE_LINE = re.compile(r'^Response (\S+): "(.*)"(?: \([^)]*\))?$', re.MULTILINE)


def _quotes(diagnostic) -> list[tuple[str, str]]:
    return QUOTE_LINE.findall(diagnostic.evidence_needed)


def test_d1_and_d2_carry_exact_excerpts_and_d3_does_not(run) -> None:
    answers = {r.id: r.answer_text for r in run.session.scalars(select(ResponseRecord))}
    d1, d2, d3 = run.report.current_version.content.diagnostics
    for diagnostic in (d1, d2):
        quotes = _quotes(diagnostic)
        assert 1 <= len(quotes) <= 3
        assert {response_id for response_id, _ in quotes} <= set(diagnostic.evidence_response_ids)
        for response_id, quote in quotes:
            assert quote and len(quote) <= 300
            assert quote in answers[response_id]
    assert not _quotes(d3)
    for line in d2.evidence_needed.splitlines():
        if line.startswith("Response "):  # each D2 quote names the brand or says that it does not
            quote = QUOTE_LINE.match(line).group(2)
            assert "kasparro" in quote.casefold() or "does not name Kasparro" in line
    assert "weakly" in d1.evidence_needed


def test_excerpts_are_deterministic(run) -> None:
    from backend.app.reports import _initial_content

    first = _initial_content(run.session, run.analysis.analysis_id)
    second = _initial_content(run.session, run.analysis.analysis_id)
    assert first.diagnostics[0].evidence_needed == second.diagnostics[0].evidence_needed
    assert first.diagnostics[1].evidence_needed == second.diagnostics[1].evidence_needed


def test_d2_quotes_the_sentence_that_names_the_brand() -> None:
    records, answers, labels = _scenario()
    # gemini is the outlier above the branded average: the others do not name the brand
    answers["chatgpt-p1"] = answers["aimode-p1"] = "Nothing relevant is said in this answer."
    answers["gemini-p1"] = "Intro line here is long enough. See https://example.com/a.b for more. Kasparro is a tool.\nNext."
    _, diagnostics, _ = build_findings(records, answers, labels, set(), "stub")
    assert 'Response gemini-p1: "Kasparro is a tool."' in diagnostics[1].evidence_needed


def test_sentence_split_ignores_dots_inside_urls() -> None:
    from backend.app.findings import opening_sentence

    text = "Visit https://example.com/a.b/c today for details. Second sentence."
    assert opening_sentence(text)[0] == "Visit https://example.com/a.b/c today for details."


def test_long_sentence_is_a_bounded_verbatim_prefix_marked_outside_the_quote() -> None:
    from backend.app.findings import opening_sentence

    text = "word " * 200 + "end."
    quote, note = opening_sentence(text)
    assert len(quote) <= 300 and text.startswith(quote) and note == "start of the sentence"


def test_d2_outlier_answer_without_the_name_says_so_and_quotes_the_opening() -> None:
    records, answers, labels = _scenario()
    # gemini is the only engine that does not name Kasparro on the branded prompt
    answers["gemini-p1"] = "This answer talks about something else entirely, nothing more."
    _, diagnostics, _ = build_findings(records, answers, labels, set(), "stub")
    text = diagnostics[1].evidence_needed
    assert "does not name Kasparro" in text
    assert 'Response gemini-p1: "This answer talks about something else entirely, nothing more."' in text


def test_checker_flags_a_tampered_excerpt(run) -> None:
    results = list(run.session.scalars(select(ResponseClassificationRecord)))
    by_response = {r.response_id: {"status": r.status, "classification": r.classification} for r in results}
    answers = {r.id: r.answer_text for r in run.session.scalars(select(ResponseRecord))}
    content = run.report.current_version.content.model_copy(deep=True)
    for diagnostic in content.diagnostics[:2]:
        response_id, quote = _quotes(diagnostic)[0]
        diagnostic.evidence_needed = diagnostic.evidence_needed.replace(quote, quote + " tampered", 1)
        problems = check_report_evidence(content, by_response, answers)
        assert any(response_id in p and "quoted excerpt not found" in p for p in problems)
        diagnostic.evidence_needed = diagnostic.evidence_needed.replace(quote + " tampered", quote, 1)
    assert check_report_evidence(content, by_response, answers) == []


def _unnamed_prompt_scenario():
    """_scenario plus p3: branded in the mapping, but its prompt text does not name Kasparro.

    Gemini is the outlier. Its p3 answer is the one the old logic would pick first (it sorts before p1).
    """
    records, answers, labels = _scenario()
    ok = {"recommended": False, "brand_mentioned": True, "negative_characterization": False}
    for engine in ("aimode", "gemini", "chatgpt"):
        answers[f"{engine}-p0"] = "Kasparro is here" if engine != "gemini" else "Nothing relevant here."
        records.append(_record(f"{engine}-p0", engine, "p0", classification=ok))
    labels["p0"] = "branded"
    answers["gemini-p1"] = "Nothing relevant here either."
    return records, answers, labels


def test_d2_evidence_never_cites_a_prompt_that_does_not_name_the_brand() -> None:
    records, answers, labels = _unnamed_prompt_scenario()
    for named in ({"p1"}, {"p0"}, {"p0", "p1"}):
        _, diagnostics, _ = build_findings(records, answers, labels, set(), "stub", named)
        by_response = {r.response_id: r.prompt_id for r in records}
        assert diagnostics[1].evidence_response_ids
        assert all(by_response[i] in named for i in diagnostics[1].evidence_response_ids)


def test_d2_regression_unnamed_prompt_answer_is_not_chosen() -> None:
    records, answers, labels = _unnamed_prompt_scenario()
    _, before, _ = build_findings(records, answers, labels, set(), "stub")
    assert "gemini-p0" in before[1].evidence_response_ids
    _, after, _ = build_findings(records, answers, labels, set(), "stub", {"p1"})
    assert after[1].evidence_response_ids == ["gemini-p1"]


def test_d2_says_how_many_branded_prompts_do_not_name_the_brand() -> None:
    records, answers, labels = _unnamed_prompt_scenario()
    _, diagnostics, _ = build_findings(records, answers, labels, set(), "stub", {"p1"})
    text = diagnostics[1].observed_pattern
    assert (
        "1 of 2 branded-labelled prompts do not contain the name Kasparro in the prompt text; "
        "the evidence below cites only prompts that do." in text
    )
    cell = literal_name_counts(records, answers, labels)["by_engine_and_branding"]["gemini|branded"]
    assert f"named Kasparro in {cell['named']} of {cell['responses']}" in text  # engine cell unchanged


def test_d2_has_no_extra_sentence_when_every_branded_prompt_names_the_brand() -> None:
    records, answers, labels = _unnamed_prompt_scenario()
    _, diagnostics, _ = build_findings(records, answers, labels, set(), "stub", {"p0", "p1"})
    assert "do not contain" not in diagnostics[1].observed_pattern


def test_d2_falls_back_to_branded_answers_when_no_branded_prompt_names_the_brand() -> None:
    records, answers, labels = _unnamed_prompt_scenario()
    _, diagnostics, _ = build_findings(records, answers, labels, set(), "stub", set())
    assert diagnostics[1].evidence_response_ids
    assert "2 of 2 branded-labelled prompts do not contain" in diagnostics[1].observed_pattern
    assert "cites only prompts that do" not in diagnostics[1].observed_pattern


def test_prompt_named_none_behaves_as_before() -> None:
    records, answers, labels = _unnamed_prompt_scenario()
    unknown = build_findings(records, answers, labels, set(), "stub")
    every_prompt = build_findings(records, answers, labels, set(), "stub", {"p0", "p1", "p2"})
    assert [d.model_dump() for d in unknown[1]] == [d.model_dump() for d in every_prompt[1]]
    assert "do not contain" not in unknown[1][1].observed_pattern


def test_real_pack_d2_cites_only_prompts_whose_text_names_the_brand(run) -> None:
    from backend.app.models import PromptRecord

    named = {
        p.id for p in run.session.scalars(select(PromptRecord)) if "kasparro" in p.text.casefold()
    }
    prompt_of = {r.id: r.prompt_id for r in run.session.scalars(select(ResponseRecord))}
    d2 = run.report.current_version.content.diagnostics[1]
    assert all(prompt_of[i] in named for i in d2.evidence_response_ids)
    assert "do not contain the name Kasparro in the prompt text" in d2.observed_pattern


def test_brand_sentence_keeps_the_brand_when_nothing_before_it_has_a_space() -> None:
    from backend.app.findings import brand_sentence

    text = "x" * 295 + "Kasparro is named here, then more words follow in this long sentence."
    quote, note = brand_sentence(text)
    assert "Kasparro" in quote and quote in text and len(quote) <= 300 and note


def test_brand_sentence_keeps_the_brand_when_the_last_space_is_before_its_word_ends() -> None:
    from backend.app.findings import brand_sentence

    text = "xx " * 95 + "Kasparroxxxxxxxxxxxxxxxxxxxx help teams, and many more words follow in this long sentence."
    quote, note = brand_sentence(text)
    assert "Kasparro" in quote and quote in text and len(quote) <= 300 and note


def test_brand_sentence_far_into_a_long_sentence_is_a_marked_part() -> None:
    from backend.app.findings import brand_sentence

    text = "word " * 200 + "Kasparro is a tool " + "word " * 100 + "end."
    quote, note = brand_sentence(text)
    assert "Kasparro" in quote and quote in text and len(quote) <= 300
    assert note == "part of the sentence"
    assert "part of the sentence" not in quote


def test_d3_title_is_true_for_a_plain_stub_run() -> None:
    # in stub mode the classified answers need not name the brand, so the title may not say they do
    records, answers, labels = _scenario()
    _, diagnostics, _ = build_findings(records, answers, labels, set(), "stub")
    title = diagnostics[2].title
    assert diagnostics[2].id == "model-findings"
    assert "name Kasparro" not in title and "stub" in title


def test_coverage_says_successful_not_valid_for_rule_and_model_results() -> None:
    _, diagnostics, _ = build_findings(*_scenario(), set(), "stub")
    for diagnostic in diagnostics[:2]:
        assert "successful," in diagnostic.observed_pattern
        assert "valid" not in diagnostic.observed_pattern


def test_remedy_two_agrees_with_d1_that_the_archive_shows_what_was_said_instead() -> None:
    _, diagnostics, remedies = build_findings(*_scenario(), set(), "stub")
    assert "cannot show what the engines say instead" not in remedies[1].problem
    assert "linked answers show what the engines say instead" in remedies[1].problem
    assert "Opening sentence" in diagnostics[0].evidence_needed
