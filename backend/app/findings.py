"""Report findings built from stored results. Pure functions: no database, no network.

Two separate number blocks are never blended:
- literal_name_counts: every archived answer, counted by exact (case-insensitive) text match.
- model_classification: only answers classified by the model, not by the literal rule.
"""
from __future__ import annotations

import re
from fractions import Fraction

from .schemas import ReportDiagnostic, ReportRemedy

ENGINE_ORDER = ("chatgpt", "gemini", "aimode")
BRANDING_ORDER = ("branded", "unbranded", "unmapped")
ENGINE_NAMES = {"chatgpt": "ChatGPT", "gemini": "Gemini", "aimode": "Google AI Mode"}
BRAND = "kasparro"
MAX_QUOTE = 300
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n")  # a dot inside a URL has no space after it


def _is_named(answer_text: str) -> bool:
    return BRAND in answer_text.casefold()


def _percent(named: int, responses: int) -> str:
    return f"{100 * named / responses:.0f}%" if responses else "n/a"


def _empty_cell() -> dict:
    return {"responses": 0, "named": 0, "absent": 0, "successful": 0, "failed": 0, "skipped": 0}


def _add(cell: dict, named: bool, status: str) -> None:
    cell["responses"] += 1
    cell["named" if named else "absent"] += 1
    cell[status] += 1


def literal_name_counts(records, answers: dict[str, str], labels: dict[str, str]) -> dict:
    """Exact count of answers naming Kasparro, with classification coverage beside every cell."""
    total = _empty_cell()
    by_engine: dict[str, dict] = {}
    by_branding: dict[str, dict] = {}
    by_cell: dict[str, dict] = {}
    for record in records:
        named = _is_named(answers[record.response_id])
        branding = labels.get(record.prompt_id, "unmapped")
        for cell in (
            total,
            by_engine.setdefault(record.engine, _empty_cell()),
            by_branding.setdefault(branding, _empty_cell()),
            by_cell.setdefault(f"{record.engine}|{branding}", _empty_cell()),
        ):
            _add(cell, named, record.status)
    return {
        "method": "Case-insensitive text match for 'Kasparro' in the archived answer; all responses.",
        "total": total,
        "by_engine": by_engine,
        "by_prompt_branding": by_branding,
        "by_engine_and_branding": by_cell,
    }


def model_classification(records, rule_response_ids: set[str], execution_mode: str) -> dict:
    """Counts over answers the model classified. Answers settled by the literal rule are excluded."""
    model_records = [
        record
        for record in records
        if record.response_id not in rule_response_ids and record.status != "skipped"
    ]
    valid = [record for record in model_records if record.status == "successful"]
    failed = [record for record in model_records if record.status == "failed"]
    quote_rejections = sum("supporting_excerpts" in (record.reason or "") for record in failed)
    recommended = sum(record.classification["recommended"] for record in valid)
    notes = []
    if model_records:
        notes.append(
            f"{len(failed)} of {len(model_records)} model calls failed "
            f"({quote_rejections} were rejected because the quoted text did not match the answer "
            "exactly). A failed call is not brand absence."
        )
    if valid:
        held_out = (
            "; on the 8-case held-out check only 5 of 8 cases gave a valid answer, and the model "
            "found 0 recommendations among them"
            if "hosted" in execution_mode
            else ""
        )
        notes.append(
            f"Only {recommended} of {len(valid)} successful model results recommended Kasparro. "
            f"This may mean the model under-detects recommendations{held_out}."
        )
    return {
        "method": (
            "Model block: successful or failed results whose answer was not settled by the "
            "literal absence rule (those have a model attempt with execution mode 'rules')."
        ),
        "execution_mode": execution_mode,
        "calls": {
            "valid": len(valid),
            "failed": len(failed),
            "skipped": sum(record.status == "skipped" for record in records),
            "quote_rejections": quote_rejections,
        },
        "mentioned_only": sum(
            record.classification["brand_mentioned"] and not record.classification["recommended"]
            for record in valid
        ),
        "recommended": recommended,
        "negative": sum(record.classification["negative_characterization"] for record in valid),
        "notes": notes,
    }


def branded_outlier_engine(literal: dict) -> str:
    """The engine whose name rate on branded prompts is furthest from the branded average.

    Ties break by engine order (chatgpt, gemini, aimode).
    """
    branded = literal["by_prompt_branding"]["branded"]
    average = Fraction(branded["named"], branded["responses"])
    gaps = []
    for key, cell in literal["by_engine_and_branding"].items():
        engine, branding = key.split("|")
        if branding == "branded":
            order = ENGINE_ORDER.index(engine) if engine in ENGINE_ORDER else len(ENGINE_ORDER)
            gaps.append((-abs(Fraction(cell["named"], cell["responses"]) - average), order, engine))
    return min(gaps)[2]


def _evidence_ids(records, keep) -> list[str]:
    """Up to three response IDs, successful results first, in a fixed order."""
    chosen = sorted(
        (record for record in records if keep(record)),
        key=lambda record: (record.status != "successful", record.response_id),
    )
    return [record.response_id for record in chosen[:3]]


def _sentences(text: str):
    """(start, end) of each non-blank sentence or line, trimmed. Slices of text are exact substrings."""
    start = 0
    for match in [*SENTENCE_BREAK.finditer(text), re.search(r"\Z", text)]:
        piece = text[start : match.start()]
        if piece.strip():
            lead = len(piece) - len(piece.lstrip())
            yield start + lead, start + len(piece.rstrip())
        start = match.end()


def _bounded(text: str, start: int, end: int, keep: int | None = None) -> tuple[str, str]:
    """Exact slice of text[start:end], at most MAX_QUOTE chars. The note says if it is not the whole sentence."""
    if end - start <= MAX_QUOTE:
        return text[start:end], ""
    note = "start of the sentence"
    brand_end = start  # the quote must reach at least this far
    if keep is not None:
        brand_end = keep + len(BRAND)
        if brand_end > start + MAX_QUOTE:  # move the window forward so it holds the brand name
            earliest = brand_end - MAX_QUOTE
            begin = max(start, keep - 100, earliest)
            space = text.rfind(" ", earliest, begin)
            start = space + 1 if space != -1 else begin
            note = "part of the sentence"
    cut = text.rfind(" ", max(start, brand_end), start + MAX_QUOTE)
    return text[start : cut if cut > start else start + MAX_QUOTE], note


def opening_sentence(text: str) -> tuple[str, str]:
    """The first sentence with at least 20 characters (else the first), as (exact quote, note)."""
    spans = list(_sentences(text))
    span = next((s for s in spans if s[1] - s[0] >= 20), spans[0] if spans else (0, 0))
    return _bounded(text, *span)


def brand_sentence(text: str) -> tuple[str, str] | None:
    """The sentence that contains the brand name (case-insensitive), as (exact quote, note)."""
    found = re.search(BRAND, text, re.IGNORECASE)
    if not found:
        return None
    start, end = next(s for s in _sentences(text) if s[1] > found.start())
    return _bounded(text, start, end, found.start())


def _quote_line(response_id: str, quote: str, note: str) -> str:
    return f'Response {response_id}: "{quote}"' + (f" ({note})" if note else "")


def _coverage(cell: dict) -> str:
    # successful covers answers settled by the literal rule and by the model; the cells do not split them
    return f"{cell['successful']} successful, {cell['failed']} failed, {cell['skipped']} skipped"


def _diagnostics(
    literal: dict, model: dict, records, answers, labels, valid_model_results, prompt_named=None
) -> list[ReportDiagnostic]:
    cells = literal["by_engine_and_branding"]
    unbranded = literal["by_prompt_branding"]["unbranded"]
    branded = literal["by_prompt_branding"]["branded"]

    # D1: unbranded prompts, all engines combined, with the per-engine split.
    split = "; ".join(
        f"{ENGINE_NAMES.get(key.split('|')[0], key.split('|')[0])} {cell['named']} of {cell['responses']}"
        for key, cell in sorted(
            cells.items(),
            key=lambda item: ENGINE_ORDER.index(item[0].split("|")[0])
            if item[0].split("|")[0] in ENGINE_ORDER
            else len(ENGINE_ORDER),
        )
        if key.endswith("|unbranded")
    )
    unbranded_ids: list[str] = []
    for engine in ENGINE_ORDER:  # one answer per engine first, so the evidence is not one engine only
        unbranded_ids += _evidence_ids(
            records,
            lambda r: r.engine == engine
            and labels.get(r.prompt_id) == "unbranded"
            and not _is_named(answers[r.response_id]),
        )[:1]
    unbranded_ids += [
        i
        for i in _evidence_ids(
            records, lambda r: labels.get(r.prompt_id) == "unbranded" and not _is_named(answers[r.response_id])
        )
        if i not in unbranded_ids
    ]
    if not unbranded_ids:  # every unbranded answer names the brand: cite any unbranded answers
        unbranded_ids = _evidence_ids(records, lambda r: labels.get(r.prompt_id) == "unbranded")
    d1 = ReportDiagnostic(
        id="unbranded-name-rate",
        title=(
            "Kasparro is never named when the prompt does not name it"
            if unbranded["named"] == 0
            else f"Kasparro is named in {unbranded['named']} of {unbranded['responses']} answers "
            "to prompts that do not name it"
        ),
        observed_pattern=(
            f"Across all engines, Kasparro was named in {unbranded['named']} of {unbranded['responses']} "
            f"answers to unbranded prompts ({_percent(unbranded['named'], unbranded['responses'])}). "
            f"By engine: {split}. Classification coverage: {_coverage(unbranded)}."
        ),
        possible_explanation=(
            "Hypothesis, not verified: when a prompt does not contain the brand name, the engines may "
            "have no reason to name it. Engine behaviour and the chosen prompts cannot be told apart "
            "from this archive alone."
        ),
        evidence_needed=(
            "Read the linked answers and list which brands each names instead. Repeat the same prompts "
            "with the name added, and compare name rates with their counts.\n"
            "Opening sentence of each linked answer. It shows what the engine said instead of naming "
            "Kasparro and proves absence only weakly; the exact count over the whole answer is what "
            "proves absence. The quotes prove the words are in the archive, not what they mean.\n"
            + "\n".join(
                _quote_line(i, *opening_sentence(answers[i])) for i in unbranded_ids[:3]
            )
        ),
        uncertainty="high",
        evidence_response_ids=unbranded_ids[:3],
    )

    # D2: the branded-prompt engine furthest from the branded average.
    engine = branded_outlier_engine(literal)
    cell = cells[f"{engine}|branded"]
    name = ENGINE_NAMES.get(engine, engine)
    above = Fraction(cell["named"], cell["responses"]) > Fraction(branded["named"], branded["responses"])
    engine_branded = [r for r in records if r.engine == engine and labels.get(r.prompt_id) == "branded"]
    # Cite only answers to prompts whose text names the brand; if there are none, cite any branded ones.
    cite_named_only = prompt_named is not None and any(r.prompt_id in prompt_named for r in engine_branded)
    cited = [r for r in engine_branded if not cite_named_only or r.prompt_id in prompt_named]
    branded_ids = _evidence_ids(
        cited, lambda r: _is_named(answers[r.response_id]) == above
    ) or _evidence_ids(cited, lambda r: True)
    unnamed_note = ""
    if prompt_named is not None:
        branded_prompts = {r.prompt_id for r in engine_branded}
        without_name = len(branded_prompts - prompt_named)
        if without_name:
            unnamed_note = (
                f" {without_name} of {len(branded_prompts)} branded-labelled prompts do not contain "
                "the name Kasparro in the prompt text"
                + ("; the evidence below cites only prompts that do." if cite_named_only else ".")
            )
    def branded_line(response_id: str) -> str:
        found = brand_sentence(answers[response_id])
        if found:
            return _quote_line(response_id, *found)
        quote, note = opening_sentence(answers[response_id])
        return _quote_line(
            response_id, quote, "; ".join(["opening sentence", "this answer does not name Kasparro"] + ([note] if note else []))
        )

    d2 = ReportDiagnostic(
        id="branded-engine-gap",
        title=f"{name} is furthest from the branded-prompt average",
        observed_pattern=(
            f"On branded prompts, {name} named Kasparro in {cell['named']} of {cell['responses']} "
            f"answers ({_percent(cell['named'], cell['responses'])}); all engines together named it in "
            f"{branded['named']} of {branded['responses']} ({_percent(branded['named'], branded['responses'])}). "
            f"Classification coverage for {name}: {_coverage(cell)}."
            + unnamed_note
        ),
        possible_explanation=(
            "Hypothesis, not verified: the engines may differ in how often they repeat a brand named in "
            f"the prompt. With one archive and {cell['responses']} branded answers for {name}, a small gap "
            "can be chance."
        ),
        evidence_needed=(
            "Read the linked answers to see how each engine handles the named brand. Repeat the "
            "branded prompts and compare the gap with its counts.\n"
            f"Sentence from each linked {name} answer that names Kasparro (or, if it does not, its "
            "opening sentence). The quotes prove the words are in the archive, not what they mean.\n"
            + "\n".join(branded_line(i) for i in branded_ids[:3])
        ),
        uncertainty="high",
        evidence_response_ids=branded_ids[:3],
    )

    # D3: what the model found on its valid answers.
    calls = model["calls"]
    attempted = calls["valid"] + calls["failed"]
    d3 = ReportDiagnostic(
        id="model-findings",
        title=f"What the classifier found in the answers it read (execution mode: {model['execution_mode']})",
        observed_pattern=(
            f"Of {calls['valid']} successful model results, {model['mentioned_only']} mention Kasparro without "
            f"recommending it and {model['recommended']} recommend it. {model['negative']} describe it "
            f"negatively (this overlaps the others). Coverage: {calls['valid']} successful; "
            f"{calls['failed']} of {attempted} model calls failed; {calls['skipped']} answers were not sent."
        ),
        possible_explanation=f"Hypothesis, not verified: {model['notes'][-1]}",
        evidence_needed=(
            "A reviewer reads the linked answers and marks mention, recommendation and negative "
            "wording without seeing the model label. Compare with the model's counts."
        ),
        uncertainty="high",
        evidence_response_ids=[r.response_id for r in valid_model_results[:3]],
    )
    return [d1, d2, d3]


def _remedies(literal, model, records, answers, labels, valid_model_results, diagnostics) -> list[ReportRemedy]:
    shared = diagnostics[0].evidence_response_ids[0]

    def linked(ids: list[str]) -> list[str]:
        # tools/check_report_evidence.py needs every remedy to share evidence with a diagnostic.
        diagnostic_ids = {i for d in diagnostics for i in d.evidence_response_ids}
        return ids if diagnostic_ids & set(ids) else ids[:2] + [shared]

    calls = model["calls"]
    attempted = calls["valid"] + calls["failed"]
    unbranded = literal["by_prompt_branding"]["unbranded"]
    scope = "unbranded prompts"
    failed_ids = _evidence_ids(
        records, lambda r: r.status == "failed" and "supporting_excerpts" in (r.reason or "")
    ) or _evidence_ids(records, lambda r: r.status == "failed")
    model_ids = [r.response_id for r in valid_model_results[:3]]
    if calls["quote_rejections"]:
        first = ReportRemedy(
            id="review-failures",
            priority=1,
            title="Fix the model quote-failure path",
            problem=(
                f"{calls['failed']} of {attempted} model calls failed, and {calls['quote_rejections']} "
                "of those failed because the quoted text did not match the archived answer exactly. "
                "Each failed answer is missing from the model results. A failure is not brand absence."
            ),
            evidence_response_ids=linked(failed_ids),
            action=(
                "Change the model reply so it returns sentence numbers instead of quoted text. "
                "The code then copies the exact sentence from the archived answer. Develop and test "
                "this only on the labelled development cases."
            ),
            expected_benefit=(
                "More named answers get a valid classification. It does not change what the model "
                "decides, and it makes no promise about ranking or visibility."
            ),
            effort="medium",
            uncertainty="medium",
            validation_step=(
                f"With the owner's approval, re-run the {calls['failed']} failed answers. Success is "
                f"the number that now validate out of {calls['failed']}, and every excerpt is still "
                "found word for word in its answer."
            ),
        )
    elif calls["failed"]:
        first = ReportRemedy(
            id="review-failures",
            priority=1,
            title="Find out why some model calls failed",
            problem=(
                f"{calls['failed']} of {attempted} model calls failed, and 0 of those failed because of "
                "a quote mismatch. Each failed answer is missing from the model results. A failure "
                "is not brand absence."
            ),
            evidence_response_ids=linked(failed_ids),
            action="An analyst reads the stored failure reason of each linked answer and groups them by cause.",
            expected_benefit="Shows whether the failures can be fixed or only retried. It makes no promise about ranking.",
            effort="low",
            uncertainty="medium",
            validation_step=(
                f"With the owner's approval, re-run the {calls['failed']} failed answers and report "
                f"how many now validate out of {calls['failed']}."
            ),
        )
    else:
        first = ReportRemedy(
            id="review-failures",
            priority=1,
            title="Keep watching for model call failures",
            problem=(
                f"0 of {attempted} model calls failed and 0 were rejected for a quote mismatch, so "
                "there is no failure path to fix in this archive."
            ),
            evidence_response_ids=linked(model_ids),
            action=(
                "Make no change now. On each new run, report failed calls out of attempted calls, "
                "so a failure is never read as brand absence."
            ),
            expected_benefit="A later rise in failures is seen at once instead of hidden in the counts.",
            effort="low",
            uncertainty="low",
            validation_step=f"On the next run, compare the failed count with 0 of {attempted} today.",
        )
    return [
        first,
        ReportRemedy(
            id="unbranded-coverage",
            priority=2,
            title="Study the prompts where Kasparro is not named",
            problem=(
                f"Kasparro is named in {unbranded['named']} of {unbranded['responses']} answers to "
                f"{scope}. "
                + (
                    "It is never named there, so "
                    if unbranded["named"] == 0
                    else f"In the {unbranded['absent']} answers that do not name it, "
                )
                + "the linked answers show what the engines say instead, but the archive does not show "
                "why, or which brands the engines name across all answers."
            ),
            evidence_response_ids=linked(
                _evidence_ids(
                    records,
                    lambda r: labels.get(r.prompt_id) == "unbranded"
                    and not _is_named(answers[r.response_id]),
                )
            ),
            action=(
                "An analyst reads the linked answers and lists which brands they name instead. Then "
                "a larger, reviewed set of unbranded prompts is archived with the same engines."
            ),
            expected_benefit=(
                "Shows whether the gap comes from prompt wording or from the engines. It makes no "
                "promise that any change will improve ranking."
            ),
            effort="medium",
            uncertainty="high",
            validation_step=(
                f"On a new archived sample, report how many answers to {scope} name Kasparro, out of how "
                f"many, and compare with {unbranded['named']} of {unbranded['responses']} today."
            ),
        ),
        ReportRemedy(
            id="review-recommendations",
            priority=3,
            title="Check recommendation counts by hand",
            problem=(
                f"Only {model['recommended']} of {calls['valid']} successful model results recommended "
                "Kasparro. The model may be missing recommendations, so this count should "
                "not be trusted yet."
            ),
            evidence_response_ids=linked(model_ids),
            action=(
                f"A reviewer reads all {calls['valid']} successful model-classified answers and marks "
                "which ones recommend Kasparro, without seeing the model label first."
            ),
            expected_benefit=(
                "Shows whether the recommendation count is too low before anyone relies on it."
            ),
            effort="low",
            uncertainty="medium",
            validation_step=(
                f"Count the answers the reviewer marks as recommendations and compare with the "
                f"model's {model['recommended']}. Report the disagreements out of {calls['valid']}."
            ),
        ),
    ]


def build_findings(
    records,
    answers: dict[str, str],
    labels: dict[str, str],
    rule_response_ids: set[str],
    execution_mode: str,
    prompt_named: set[str] | None = None,
) -> tuple[dict, list[ReportDiagnostic], list[ReportRemedy]]:
    """Return the two summary blocks, three diagnostics and three remedies for one analysis.

    prompt_named: ids of prompts whose own text contains the brand name; None means unknown, so
    every branded prompt is treated as naming it.
    """
    literal = literal_name_counts(records, answers, labels)
    if not {"branded", "unbranded"} <= set(literal["by_prompt_branding"]):
        raise ValueError("Diagnostics need both branded and unbranded prompts; prompt types are not mapped")
    model = model_classification(records, rule_response_ids, execution_mode)
    valid_model_results = sorted(
        (r for r in records if r.status == "successful" and r.response_id not in rule_response_ids),
        key=lambda r: (not r.classification["recommended"], r.response_id),
    )
    if not valid_model_results:
        raise ValueError("Diagnostics need at least one valid model-classified answer")
    diagnostics = _diagnostics(literal, model, records, answers, labels, valid_model_results, prompt_named)
    remedies = _remedies(literal, model, records, answers, labels, valid_model_results, diagnostics)
    return {"literal_name_counts": literal, "model_classification": model}, diagnostics, remedies
