#!/usr/bin/env python3
"""Benchmark only the frozen development split; held-out cases are intentionally inaccessible."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.classification import GroqClassifier, OllamaClassifier  # noqa: E402
from backend.app.config import Settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("ollama", "groq"), default="ollama")
    parser.add_argument("--response-id")
    parser.add_argument("--context-tokens", type=int, default=16384)
    args = parser.parse_args()
    settings = Settings.from_environment()

    labels = json.loads((ROOT / "evaluation" / "labels-v1.json").read_text(encoding="utf-8"))
    development = {
        case["response_id"]: case
        for case in labels["supplied_cases"]
        if case["split"] == "development"
    }
    responses = {
        row["response_id"]: row
        for row in (
            json.loads(line)
            for line in (ROOT / "data" / "responses.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    if args.response_id:
        if args.response_id not in development:
            parser.error("--response-id must identify a frozen development case")
        selected_ids = [args.response_id]
    else:
        selected_ids = sorted(development, key=lambda item: len(responses[item]["answer_text"]))

    if args.provider == "ollama":
        classifier = OllamaClassifier(
            context_tokens=args.context_tokens,
            max_input_chars=settings.max_input_chars,
        )
    else:
        if not settings.groq_api_key:
            parser.error(
                "GROQ_API_KEY is blank or unavailable. Add it to the root .env or process environment."
            )
        classifier = GroqClassifier(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            max_input_chars=settings.max_input_chars,
        )

    records = []
    all_validated = True
    for response_id in selected_ids:
        source = responses[response_id]
        expected = development[response_id]["expected"]
        outcome = classifier.classify(source["answer_text"], response_id)
        actual = outcome.result.model_dump(mode="json") if outcome.result else None
        agreement = None
        if actual is not None:
            agreement = {
                field: actual[field] == expected[field]
                for field in (
                    "brand_mentioned",
                    "recommended",
                    "negative_characterization",
                    "observable_position",
                )
            }
        passed = actual is not None and agreement is not None and all(agreement.values())
        all_validated = all_validated and passed
        records.append(
            {
                "response_id": response_id,
                "engine": source["engine"],
                "input_chars": len(source["answer_text"]),
                "model_identifier": outcome.model_identifier,
                "validated": outcome.result is not None,
                "label_agreement": agreement,
                "passed": passed,
                "attempts": [attempt.__dict__ for attempt in outcome.attempts],
                "result": actual,
            }
        )
    print(
        json.dumps(
            {
                "split": "development",
                "provider": args.provider,
                "cases": records,
                "all_passed": all_validated,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if all_validated else 1


if __name__ == "__main__":
    raise SystemExit(main())
