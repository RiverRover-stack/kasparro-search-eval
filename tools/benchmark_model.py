#!/usr/bin/env python3
"""Run one representative archived answer through the bounded local classifier."""
from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.classification import OllamaClassifier, visibility_score  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sample",
        choices=("median", "largest"),
        default="median",
        help="Select the median-length or maximum-length supplied response.",
    )
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in (ROOT / "data" / "responses.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ordered = sorted(rows, key=lambda row: len(row["answer_text"]))
    sample = ordered[-1] if args.sample == "largest" else ordered[len(rows) // 2]
    outcome = OllamaClassifier().classify(sample["answer_text"])
    output = {
        "response_id": sample["response_id"],
        "selection": args.sample,
        "input_chars": len(sample["answer_text"]),
        "model": outcome.model_identifier,
        "prompt_version": outcome.prompt_version,
        "attempts": [attempt.__dict__ for attempt in outcome.attempts],
        "validated": outcome.result is not None,
        "result": outcome.result.model_dump(mode="json") if outcome.result else None,
        "visibility_score": visibility_score(outcome.result) if outcome.result else None,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if outcome.result else 1


if __name__ == "__main__":
    raise SystemExit(main())

