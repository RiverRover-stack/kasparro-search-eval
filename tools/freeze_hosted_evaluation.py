#!/usr/bin/env python3
"""Freeze the successful development configuration before held-out evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.classification import (  # noqa: E402
    CLASSIFICATION_CONTRACT_VERSION,
    PROMPT_VERSION,
)
from backend.app.config import Settings  # noqa: E402


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_development_result(document: dict[str, object], expected_model: str) -> None:
    cases = document.get("cases")
    if document.get("split") != "development" or document.get("provider") != "groq":
        raise ValueError("Development artifact must be a Groq development result")
    if document.get("all_passed") is not True:
        raise ValueError("Development artifact has not passed all cases")
    if not isinstance(cases, list) or len(cases) != 4:
        raise ValueError("Development artifact must contain exactly four cases")
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Development artifact contains an invalid case")
        if case.get("model_identifier") != expected_model:
            raise ValueError("Every development case must use the configured frozen model")
        if case.get("validated") is not True or case.get("passed") is not True:
            raise ValueError("Every development case must be validated and passed")
        agreement = case.get("label_agreement")
        if not isinstance(agreement, dict) or not agreement or not all(
            value is True for value in agreement.values()
        ):
            raise ValueError("Every development label must agree with its frozen expectation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--development-result",
        type=Path,
        default=ROOT / "evaluation" / "groq-development-120b.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evaluation" / "frozen-hosted-config-v1.json",
    )
    args = parser.parse_args()

    development_path = args.development_result.resolve()
    output_path = args.output.resolve()
    if output_path.exists():
        parser.error(f"freeze manifest already exists: {output_path}")
    settings = Settings.from_environment()
    document = json.loads(development_path.read_text(encoding="utf-8-sig"))
    validate_development_result(document, settings.groq_model)

    classification_path = ROOT / "backend" / "app" / "classification.py"
    labels_path = ROOT / "evaluation" / "labels-v1.json"
    runner_path = ROOT / "tools" / "benchmark_held_out.py"
    manifest = {
        "freeze_version": "hosted-evaluation-freeze-v1",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "groq",
        "model_identifier": settings.groq_model,
        "prompt_version": PROMPT_VERSION,
        "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "generation_settings": {
            "temperature": 0,
            "seed": 17,
            "reasoning_effort": "low",
            "max_completion_tokens": 2048,
        },
        "development_result": str(development_path.relative_to(ROOT)).replace("\\", "/"),
        "development_result_sha256": sha256_file(development_path),
        "classifier_source_sha256": sha256_file(classification_path),
        "labels_sha256": sha256_file(labels_path),
        "held_out_runner_sha256": sha256_file(runner_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen manifest written to {output_path}")
    print(f"Model: {settings.groq_model}")
    print(f"Prompt: {PROMPT_VERSION}")
    print("No API key was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
