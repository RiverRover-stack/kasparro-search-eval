#!/usr/bin/env python3
"""Compare a keyword baseline with the frozen Groq results on the same labelled cases. No network."""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend.app.analysis import execute_analysis  # noqa: E402
from backend.app.classification import (  # noqa: E402
    ClassificationResult,
    ControlledStubClassifier,
    visibility_score,
)
from backend.app.database import Base  # noqa: E402
from backend.app.importer import import_pack  # noqa: E402
from backend.app.models import ResponseClassificationRecord, ResponseRecord  # noqa: E402
from backend.app.reports import create_report  # noqa: E402
from tools.benchmark_held_out import FIELDS, build_summary  # noqa: E402
from tools.check_report_evidence import QUOTE_LINE, check_report_evidence  # noqa: E402
from tools.rule_baseline import baseline_labels  # noqa: E402

EVALUATION = ROOT / "evaluation"
LIMITS = (
    "The labels are the project owner's own, not an independent annotation.",
    "Only four fields are compared: brand_mentioned, recommended, negative_characterization and observable_position. Competitors and excerpt choice are not graded.",
    "The held-out set is 8 cases and contains one positive recommendation case, so recommended precision and recall rest on very little.",
    "The model results come from a single frozen run. Repeatability is unverified, so every model-quality statement here is single-run and unverified.",
    "The baseline cue lists were fixed before the first evaluation run and were not changed afterwards.",
    "No LLM judges anything here; every comparison is a deterministic rule against the owner's labels.",
    "Quote traceability (an excerpt occurs verbatim in the answer) is not semantic correctness.",
)
MODEL_LABEL = "Model (one recorded run; repeatability not tested)"
ENGINE_NAMES = {"chatgpt": "ChatGPT", "gemini": "Gemini", "aimode": "Google AI Mode"}
EXECUTION_MODES = {
    "baseline": "rules baseline (tools/rule_baseline.py), no model",
    "model": "frozen hosted_groq artifact (openai/gpt-oss-120b), read from evaluation/, not rerun",
}


def expected_fields(expected: dict) -> dict:
    return {field: expected[field] for field in FIELDS}


def labels_agree(expected: dict, actual: dict) -> bool:
    return all(actual[field] == expected[field] for field in FIELDS)


def baseline_records(cases: list[dict], answers: dict[str, str]) -> list[dict]:
    records = []
    for case in cases:
        text = answers[case["response_id"]] if "response_id" in case else case["answer_text"]
        expected = expected_fields(case["expected"])
        result = baseline_labels(text)
        records.append(
            {"validated": True, "expected": expected, "result": result, "passed": labels_agree(expected, result)}
        )
    return records


def model_records(artifact: dict, expected_by_response: dict[str, dict]) -> list[dict]:
    records = []
    for case in artifact["cases"]:
        expected = case.get("expected") or expected_by_response[case["response_id"]]
        records.append(
            {
                "validated": case["validated"],
                "expected": expected_fields(expected),
                "result": case["result"],
                "passed": case["passed"],
            }
        )
    return records


def recomputed_passed(record: dict) -> bool:
    return bool(record["validated"]) and labels_agree(record["expected"], record["result"])


def failed_cases(artifact: dict) -> list[dict]:
    failures = []
    for case in artifact["cases"]:
        if not case["validated"]:
            error = " ".join((case["attempts"][-1].get("validation_error") or "").split())[:160] if case["attempts"] else ""
            failures.append({"response_id": case["response_id"], "last_attempt_error": error})
    return failures


def independent_score(brand_mentioned: bool, recommended: bool) -> int:
    if recommended:
        return 100
    return 25 if brand_mentioned else 0


def build_result(**values) -> ClassificationResult:
    base = {
        "contract_version": "classification-v1",
        "brand_mentioned": False,
        "recommended": False,
        "negative_characterization": False,
        "competitors": [],
        "observable_position": None,
        "supporting_excerpts": [],
        "uncertainty": "low",
        "uncertainty_reason": "score arithmetic check",
    }
    return ClassificationResult.model_validate(base | values)


def check_score_arithmetic(expected_labels: list[dict], model_results: list[dict]) -> dict:
    candidates: list[ClassificationResult] = []
    for brand, recommended, negative in itertools.product((False, True), repeat=3):
        try:
            candidates.append(
                build_result(
                    brand_mentioned=brand, recommended=recommended, negative_characterization=negative
                )
            )
        except ValueError:
            continue
    combinations = len(candidates)
    for labels in expected_labels:
        try:
            candidates.append(build_result(**expected_fields(labels)))
        except ValueError:
            continue
    from_expected = len(candidates) - combinations
    candidates.extend(ClassificationResult.model_validate(result) for result in model_results)
    mismatches = sum(
        visibility_score(item) != independent_score(item.brand_mentioned, item.recommended)
        for item in candidates
    )
    return {
        "checked": len(candidates),
        "contract_allowed_combinations": combinations,
        "from_expected_labels": from_expected,
        "from_validated_model_results": len(candidates) - combinations - from_expected,
        "mismatches": mismatches,
    }


def seeded_defect_check() -> dict:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        dataset = import_pack(session, ROOT)
        analysis = execute_analysis(session, dataset.dataset_id, ControlledStubClassifier(), 20_000)
        report = create_report(session, analysis.analysis_id, "analyst", "evaluation-harness")
        content = report.current_version.content.model_dump()
        results = {
            row.response_id: {"status": row.status, "classification": row.classification}
            for row in session.scalars(
                select(ResponseClassificationRecord).where(
                    ResponseClassificationRecord.analysis_run_id == analysis.analysis_id
                )
            )
        }
        answers = {row.id: row.answer_text for row in session.scalars(select(ResponseRecord))}

    clean = check_report_evidence(content, results, answers)
    linked = content["diagnostics"][1]["evidence_response_ids"][0]
    spare = next(response_id for response_id in sorted(results) if response_id != linked)

    unknown = deepcopy(content)
    unknown["diagnostics"][1]["evidence_response_ids"] = ["not-in-analysis"]
    failed_results = deepcopy(results)
    failed_results[linked]["status"] = "failed"
    bad_quote_results = deepcopy(results)
    bad_quote_results[linked]["classification"] = {
        "supporting_excerpts": [{"kind": "mention", "quote": "text that is not in the answer"}]
    }
    no_overlap = deepcopy(content)
    for item in no_overlap["diagnostics"]:
        item["evidence_response_ids"] = [linked]
    no_overlap["remedies"][1]["evidence_response_ids"] = [spare]

    empty_quote = deepcopy(content)
    empty_quote["diagnostics"][0]["evidence_needed"] = QUOTE_LINE.sub(
        lambda found: f'Response {found.group(1)}: ""', empty_quote["diagnostics"][0]["evidence_needed"], count=1
    )

    seeded = {
        "evidence_id_not_in_analysis": check_report_evidence(unknown, results, answers),
        "failed_result_in_non_failure_section": check_report_evidence(content, failed_results, answers),
        "excerpt_not_in_answer": check_report_evidence(content, bad_quote_results, answers),
        "remedy_without_shared_evidence": check_report_evidence(no_overlap, results, answers),
        "empty_quote": check_report_evidence(empty_quote, results, answers),
    }
    return {
        "label": "STUB analysis, mechanics only, not model quality",
        "execution_mode": "stub",
        "results_checked": len(results),
        "clean_problems": clean,
        "seeded_defects_flagged": {name: bool(found) for name, found in seeded.items()},
        "seeded_defect_problems": seeded,
    }


def format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


def case_name(response_id: str, labels: dict) -> str:
    """Readable name of a labelled case, for example 'Google AI Mode, prompt 004'."""
    for case in labels["supplied_cases"]:
        if case["response_id"] == response_id:
            engine = ENGINE_NAMES.get(case["engine"], case["engine"])
            return f"{engine}, prompt {case['prompt_id'].rsplit(':', 1)[-1]}"
    return "Unknown case"


def failure_reason(error: str) -> str:
    if "does not match the expected schema" in error:
        return "Groq rejected the model JSON: it did not match the required schema"
    if "Negative characterization requires a brand mention" in error:
        return "Model output broke the contract: negative characterization without a brand mention"
    return "Model call failed"


def describe_failed_case(failure: dict, labels: dict) -> str:
    return f"{case_name(failure['response_id'], labels)}: {failure_reason(failure['last_attempt_error'])}"


def metric_row(summary: dict, field: str) -> str:
    metric = summary["per_label"][field]
    if field == "observable_position":
        return f"| {field} | {format_metric(metric['agreement'])} | n/a | n/a | - | - | - | - |"
    counts = " | ".join(str(metric[key]) for key in ("tp", "fp", "fn", "tn"))
    return (
        f"| {field} | {format_metric(metric['agreement'])} | {format_metric(metric['precision'])} | "
        f"{format_metric(metric['recall'])} | {counts} |"
    )


def section_markdown(title: str, block: dict) -> list[str]:
    summary = block["summary"]
    lines = [
        f"### {title}",
        "",
        f"- Execution mode: {block['execution_mode']}",
        f"- Coverage (validated/total): {summary['validated_cases']}/{summary['total_cases']}",
        f"- Exact passes (all four fields): {summary['passed_cases']}/{summary['total_cases']}",
    ]
    if block.get("note"):
        lines.append(f"- Note: {block['note']}")
    lines += ["", "| Label | Agreement | Precision | Recall | TP | FP | FN | TN |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    lines += [metric_row(summary, field) for field in FIELDS]
    position = summary["per_label"]["observable_position"]
    lines += [
        "",
        f"observable_position is graded by exact equality: {position['matches']} of {summary['total_cases']} cases matched.",
        "",
    ]
    return lines


def headline_markdown(doc: dict) -> list[str]:
    lines = [
        "| System | Valid results | Coverage | Exact-match cases | brand_mentioned agreement "
        "| recommended agreement | negative_characterization agreement |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    systems = ((MODEL_LABEL, doc["model_held_out"]), ("Keyword baseline", doc["baseline_held_out"]))
    for name, block in systems:
        summary = block["summary"]
        total = summary["total_cases"]
        agreement = [format_metric(summary["per_label"][field]["agreement"]) for field in FIELDS[:3]]
        lines.append(
            f"| {name} | {summary['validated_cases']}/{total} | {format_percent(summary['validation_coverage'])} "
            f"| {summary['passed_cases']}/{total} | " + " | ".join(agreement) + " |"
        )
    return lines


def confusion_markdown(doc: dict) -> list[str]:
    model = doc["model_held_out"]["summary"]
    baseline = doc["baseline_held_out"]["summary"]
    lines = [
        "Rows are the owner's label (Actual), columns are the system's answer (Predicted). "
        "Failed model cases are excluded from the model matrices, so they cover "
        f"{model['validated_cases']} of {model['total_cases']} cases; the baseline covers all {baseline['total_cases']}.",
        "",
    ]
    for field in FIELDS[:3]:
        m, b = model["per_label"][field], baseline["per_label"][field]
        lines += [
            f"**{field}**",
            "",
            "| Actual | Model predicted yes | Model predicted no | Baseline predicted yes | Baseline predicted no |",
            "|---|---:|---:|---:|---:|",
            f"| Actual yes | {m['tp']} | {m['fn']} | {b['tp']} | {b['fn']} |",
            f"| Actual no | {m['fp']} | {m['tn']} | {b['fp']} | {b['tn']} |",
            "",
        ]
    return lines


def failed_cases_markdown(doc: dict, labels: dict) -> list[str]:
    lines = []
    for title, key in (("Held-out", "model_held_out"), ("Development", "model_development")):
        lines += [f"- {title}: {describe_failed_case(failure, labels)}" for failure in doc[key]["failed_cases"]]
    return lines or ["No failed cases."]


def markdown_report(doc: dict, labels: dict) -> str:
    held_out = doc["model_held_out"]["summary"]["total_cases"]
    development = doc["model_development"]["summary"]["total_cases"]
    synthetic = doc["baseline_synthetic"]["summary"]["total_cases"]
    cross = doc["cross_checks"]
    arithmetic = doc["score_arithmetic"]
    evidence = doc["report_evidence_check"]
    lines = [
        "# Kasparro AI visibility classifier: model versus keyword baseline",
        "",
        f"Evaluation comparison report. Label set: {labels['label_set_version']}.",
        "",
        "This report compares one frozen language model run (openai/gpt-oss-120b via Groq) with a simple keyword "
        "baseline on the same labelled cases. Both are scored against the project owner's labels for four fields "
        "of each archived AI answer. It is written for a reviewer who has not seen the project. "
        "Nothing here is run over the network; the model results are read from saved files.",
        "",
        "Caveat: single frozen model run, owner-written labels, model quality unverified.",
        "",
        f"## Headline results (held-out set, {held_out} cases)",
        "",
    ]
    lines += headline_markdown(doc)
    lines += [
        "",
        "Agreement is counted over all cases in the set, so a failed model result lowers the model's agreement.",
        "",
        "## How to read the metrics",
        "",
        "- Agreement = (TP + TN) / all cases in the set. A failed result counts as not agreeing.",
        "- Precision = TP / (TP + FP). Recall = TP / (TP + FN). Both show n/a when the denominator is zero.",
        "- TP, FP, FN, TN compare the owner's label (Actual) with the system's answer (Predicted). "
        "TP = both yes; FP = system yes, owner no; FN = system no, owner yes; TN = both no.",
        "- Coverage = validated results / total cases. A result is validated when the model output passed the contract check.",
        "- Exact match = all four fields correct for a case.",
        "- observable_position is graded by exact equality with the owner's label, not by precision and recall.",
        "- Failed results are not counted as absence: they are left out of TP, FP, FN and TN.",
        "",
        f"## Held-out final check ({held_out} cases)",
        "",
        f"- Baseline: {EXECUTION_MODES['baseline']}.",
        f"- Model: {EXECUTION_MODES['model']}. The model was not run on the synthetic cases.",
        "",
    ]
    lines += section_markdown(MODEL_LABEL, doc["model_held_out"])
    lines += section_markdown("Baseline", doc["baseline_held_out"])
    lines += ["### Confusion matrices", ""]
    lines += confusion_markdown(doc)
    lines += [f"## Development cases ({development})", ""]
    lines += section_markdown(MODEL_LABEL, doc["model_development"])
    lines += section_markdown("Baseline", doc["baseline_development"])
    lines += [f"## Synthetic edge cases ({synthetic})", "", "The model was not run on synthetic cases.", ""]
    lines += section_markdown("Baseline", doc["baseline_synthetic"])
    lines += ["## Failed cases", ""] + failed_cases_markdown(doc, labels) + [""]
    lines += [
        "## Integrity checks",
        "",
        "### Cross-checks",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Held-out artifact summary equals recomputed summary | {yes_no(cross['held_out_summary_matches_artifact'])} |",
        f"| Stored passed flags equal recomputation from labels (held-out) | {yes_no(cross['held_out_passed_flags_match'])} |",
        f"| Stored passed flags equal recomputation from labels (development) | {yes_no(cross['development_passed_flags_match'])} |",
        "",
        "The development artifact stores no summary, so only per-case passed flags are compared.",
        "",
        "### Score arithmetic",
        "",
        "Independent function (absent 0, mentioned 25, recommended 100) versus `visibility_score`.",
        "",
        f"- Checked: {arithmetic['checked']} ({arithmetic['contract_allowed_combinations']} contract-allowed boolean "
        f"combinations, {arithmetic['from_expected_labels']} from expected labels, "
        f"{arithmetic['from_validated_model_results']} from validated model results)",
        f"- Mismatches: {arithmetic['mismatches']}",
        "",
        "### Report evidence check",
        "",
        f"**{evidence['label']}**",
        "",
        f"- Results in the stub analysis: {evidence['results_checked']}",
        f"- Problems found in the clean report: {len(evidence['clean_problems'])}",
        "",
        "| Seeded defect | Flagged |",
        "|---|---|",
    ]
    lines += [f"| {name.replace('_', ' ')} | {yes_no(flagged)} |" for name, flagged in evidence["seeded_defects_flagged"].items()]
    lines += ["", "## Limits", ""]
    lines += [f"- {item}" for item in LIMITS]
    lines.append("")
    return "\n".join(lines)


def load_labels() -> dict:
    return json.loads((EVALUATION / "labels-v1.json").read_text(encoding="utf-8"))


def build_document(labels: dict) -> dict:
    answers = {
        row["response_id"]: row["answer_text"]
        for row in (
            json.loads(line)
            for line in (ROOT / "data" / "responses.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    supplied = labels["supplied_cases"]
    held_out_cases = [case for case in supplied if case["split"] == "held_out"]
    development_cases = [case for case in supplied if case["split"] == "development"]
    expected_by_response = {case["response_id"]: case["expected"] for case in supplied}
    held_out_artifact = json.loads((EVALUATION / "groq-held-out-120b.json").read_text(encoding="utf-8"))
    development_artifact = json.loads((EVALUATION / "groq-development-120b.json").read_text(encoding="utf-8"))

    model_held_out = model_records(held_out_artifact, expected_by_response)
    model_development = model_records(development_artifact, expected_by_response)
    summary_matches = build_summary(model_held_out) == held_out_artifact["summary"]
    held_out_flags = all(recomputed_passed(item) == item["passed"] for item in model_held_out)
    development_flags = all(recomputed_passed(item) == item["passed"] for item in model_development)

    def block(mode: str, records: list[dict], **extra) -> dict:
        return {"execution_mode": EXECUTION_MODES[mode], "summary": build_summary(records)} | extra

    expected_labels = [case["expected"] for case in supplied + labels["synthetic_cases"]]
    model_results = [item["result"] for item in model_held_out + model_development if item["validated"]]
    return {
        "model_held_out": block(
            "model",
            model_held_out,
            summary_matches_artifact=summary_matches,
            failed_cases=failed_cases(held_out_artifact),
        ),
        "baseline_held_out": block("baseline", baseline_records(held_out_cases, answers)),
        "model_development": block(
            "model",
            model_development,
            note="the artifact stores no expected labels or summary; expected labels come from labels-v1.json",
            failed_cases=failed_cases(development_artifact),
        ),
        "baseline_development": block("baseline", baseline_records(development_cases, answers)),
        "baseline_synthetic": block("baseline", baseline_records(labels["synthetic_cases"], answers)),
        "cross_checks": {
            "held_out_summary_matches_artifact": summary_matches,
            "held_out_passed_flags_match": held_out_flags,
            "development_passed_flags_match": development_flags,
        },
        "score_arithmetic": check_score_arithmetic(expected_labels, model_results),
        "report_evidence_check": seeded_defect_check(),
        "limits": list(LIMITS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=EVALUATION)
    args = parser.parse_args(argv)
    labels = load_labels()
    document = build_document(labels)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "comparison-report.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.output_dir / "comparison-report.md").write_text(markdown_report(document, labels), encoding="utf-8")
    print(f"Report: {args.output_dir / 'comparison-report.md'}")
    cross = document["cross_checks"]
    healthy = (
        all(cross.values())
        and document["score_arithmetic"]["mismatches"] == 0
        and not document["report_evidence_check"]["clean_problems"]
        and all(document["report_evidence_check"]["seeded_defects_flagged"].values())
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
