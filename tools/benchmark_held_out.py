#!/usr/bin/env python3
"""Run the frozen eight-case held-out evaluation exactly as configured."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.classification import (  # noqa: E402
    CLASSIFICATION_CONTRACT_VERSION,
    PROMPT_VERSION,
    GroqClassifier,
)
from backend.app.config import Settings  # noqa: E402

FIELDS = (
    "brand_mentioned",
    "recommended",
    "negative_characterization",
    "observable_position",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze(manifest: dict[str, object], settings: Settings) -> None:
    checks = {
        "model_identifier": settings.groq_model,
        "prompt_version": PROMPT_VERSION,
        "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "classifier_source_sha256": sha256_file(ROOT / "backend" / "app" / "classification.py"),
        "labels_sha256": sha256_file(ROOT / "evaluation" / "labels-v1.json"),
        "held_out_runner_sha256": sha256_file(Path(__file__).resolve()),
    }
    development_path = ROOT / str(manifest.get("development_result", ""))
    checks["development_result_sha256"] = sha256_file(development_path)
    mismatches = [key for key, actual in checks.items() if manifest.get(key) != actual]
    if mismatches:
        raise ValueError("Frozen evaluation mismatch: " + ", ".join(mismatches))


def boolean_metrics(records: list[dict[str, object]], field: str) -> dict[str, object]:
    tp = tn = fp = fn = 0
    for record in records:
        if not record.get("validated"):
            continue
        expected = bool(record["expected"][field])  # type: ignore[index]
        actual = bool(record["result"][field])  # type: ignore[index]
        if expected and actual:
            tp += 1
        elif not expected and not actual:
            tn += 1
        elif not expected and actual:
            fp += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "agreement": (tp + tn) / len(records) if records else None,
    }


def build_summary(records: list[dict[str, object]]) -> dict[str, object]:
    validated = sum(record.get("validated") is True for record in records)
    passed = sum(record.get("passed") is True for record in records)
    position_matches = sum(
        record.get("validated") is True
        and record["result"]["observable_position"]  # type: ignore[index]
        == record["expected"]["observable_position"]  # type: ignore[index]
        for record in records
    )
    return {
        "total_cases": len(records),
        "validated_cases": validated,
        "validation_coverage": validated / len(records) if records else 0,
        "passed_cases": passed,
        "exact_case_pass_rate": passed / len(records) if records else 0,
        "per_label": {
            field: boolean_metrics(records, field)
            for field in FIELDS[:3]
        }
        | {
            "observable_position": {
                "matches": position_matches,
                "agreement": position_matches / len(records) if records else 0,
            }
        },
    }


def markdown_report(document: dict[str, object]) -> str:
    summary = document["summary"]
    lines = [
        "# Frozen Groq held-out evaluation",
        "",
        f"- Model: `{document['model_identifier']}`",
        f"- Prompt: `{document['prompt_version']}`",
        f"- Validated coverage: {summary['validated_cases']}/{summary['total_cases']}",  # type: ignore[index]
        f"- Exact case passes: {summary['passed_cases']}/{summary['total_cases']}",  # type: ignore[index]
        "",
        "| Label | Agreement | Precision | Recall |",
        "|---|---:|---:|---:|",
    ]
    per_label = summary["per_label"]  # type: ignore[index]
    for field in FIELDS[:3]:
        metric = per_label[field]
        precision = "n/a" if metric["precision"] is None else f"{metric['precision']:.3f}"
        recall = "n/a" if metric["recall"] is None else f"{metric['recall']:.3f}"
        lines.append(f"| {field} | {metric['agreement']:.3f} | {precision} | {recall} |")
    position = per_label["observable_position"]
    lines.append(f"| observable_position | {position['agreement']:.3f} | n/a | n/a |")
    lines.extend(
        [
            "",
            "Held-out failures must be recorded as limitations and must not be used to tune this frozen prompt.",
            "Exact-source validation establishes traceability, not semantic correctness of an excerpt.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--freeze",
        type=Path,
        default=ROOT / "evaluation" / "frozen-hosted-config-v1.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evaluation" / "groq-held-out-120b.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "evaluation" / "groq-held-out-120b.md",
    )
    parser.add_argument("--delay-seconds", type=float, default=30.0)
    parser.add_argument("--confirm-frozen", action="store_true")
    args = parser.parse_args()
    if not args.confirm_frozen:
        parser.error("--confirm-frozen is required")
    if args.output.exists() or args.report.exists():
        parser.error("held-out output already exists; refusing to overwrite frozen evidence")

    settings = Settings.from_environment()
    if not settings.groq_api_key:
        parser.error("GROQ_API_KEY is blank or unavailable")
    manifest = json.loads(args.freeze.read_text(encoding="utf-8-sig"))
    verify_freeze(manifest, settings)

    labels = json.loads((ROOT / "evaluation" / "labels-v1.json").read_text(encoding="utf-8"))
    held_out = [case for case in labels["supplied_cases"] if case["split"] == "held_out"]
    if len(held_out) != 8:
        parser.error("frozen label set must contain exactly eight held-out cases")
    responses = {
        row["response_id"]: row
        for row in (
            json.loads(line)
            for line in (ROOT / "data" / "responses.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    classifier = GroqClassifier(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        max_input_chars=settings.max_input_chars,
    )
    records: list[dict[str, object]] = []
    for index, case in enumerate(held_out, start=1):
        response_id = case["response_id"]
        source = responses[response_id]
        print(f"Running held-out case {index}/8: {response_id}", file=sys.stderr, flush=True)
        outcome = classifier.classify(source["answer_text"], response_id)
        actual = outcome.result.model_dump(mode="json") if outcome.result else None
        expected = case["expected"]
        agreement = (
            {field: actual[field] == expected[field] for field in FIELDS}
            if actual is not None
            else None
        )
        records.append(
            {
                "response_id": response_id,
                "engine": source["engine"],
                "input_chars": len(source["answer_text"]),
                "model_identifier": outcome.model_identifier,
                "validated": actual is not None,
                "expected": {field: expected[field] for field in FIELDS},
                "result": actual,
                "label_agreement": agreement,
                "passed": agreement is not None and all(agreement.values()),
                "attempts": [attempt.__dict__ for attempt in outcome.attempts],
            }
        )
        if index < len(held_out) and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    document = {
        "split": "held_out",
        "provider": "groq",
        "model_identifier": settings.groq_model,
        "prompt_version": PROMPT_VERSION,
        "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "freeze_manifest": str(args.freeze.resolve().relative_to(ROOT)).replace("\\", "/"),
        "summary": build_summary(records),
        "cases": records,
    }
    args.output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.report.write_text(markdown_report(document), encoding="utf-8")
    print(f"JSON: {args.output}")
    print(f"Report: {args.report}")
    return 0 if document["summary"]["passed_cases"] == 8 else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
