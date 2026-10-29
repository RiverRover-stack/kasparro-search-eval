#!/usr/bin/env python3
"""Mixed live run: literal-absence rule, a fixed Groq sample, everything else skipped.

Without --confirm-send this only prints a plan and never builds a Groq client.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from backend.app.analysis import execute_analysis  # noqa: E402
from backend.app.classification import GroqClassifier, LiteralAbsenceRouter  # noqa: E402
from backend.app.classification.groq import build_payload  # noqa: E402
from backend.app.config import Settings  # noqa: E402
from backend.app.database import build_engine, build_session_factory, initialize_database  # noqa: E402
from backend.app.importer import import_pack  # noqa: E402
from backend.app.models import ModelAttemptRecord, ResponseRecord  # noqa: E402
from backend.app.sampling import SAMPLE_RULE_VERSION, select_live_sample  # noqa: E402

EXPECTED_MODEL = "openai/gpt-oss-120b"
TOKENS_PER_MINUTE = 8000
MAX_OUTPUT_TOKENS = 2048
CHARS_PER_TOKEN = 3.4
OUTPUT_PATH = ROOT / "evaluation" / "live-run-groq-sample.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-send", action="store_true")
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument(
        "--database-url",
        help="default: in-memory for the plan, the configured database for a confirmed send",
    )
    args = parser.parse_args()
    settings = Settings.from_environment()

    model_ok = settings.groq_model == EXPECTED_MODEL
    if not model_ok:
        print(
            f"WARNING: configured model is {settings.groq_model!r}, expected {EXPECTED_MODEL!r}",
            file=sys.stderr,
        )
    if args.confirm_send and not model_ok and not args.allow_model:
        print("Refusing to send; pass --allow-model to accept this model.", file=sys.stderr)
        return 1
    if args.confirm_send and OUTPUT_PATH.exists():
        print(f"Refusing to overwrite {OUTPUT_PATH}", file=sys.stderr)
        return 1

    default_url = settings.database_url if args.confirm_send else "sqlite://"
    engine = build_engine(args.database_url or default_url)
    initialize_database(engine)
    labels = json.loads((ROOT / "evaluation" / "labels-v1.json").read_text(encoding="utf-8"))
    labelled = {case["response_id"] for case in labels["supplied_cases"]}

    with build_session_factory(engine)() as session:
        dataset = import_pack(session, settings.input_pack_path)
        responses = list(
            session.scalars(
                select(ResponseRecord)
                .where(ResponseRecord.dataset_id == dataset.dataset_id)
                .order_by(ResponseRecord.id)
            )
        )
        sample = select_live_sample(responses, labelled)
        sampled = set(sample)
        by_id = {response.id: response for response in responses}
        absent = [r.id for r in responses if "kasparro" not in r.answer_text.casefold()]
        skip_reasons = {}
        for response in responses:
            if "kasparro" not in response.answer_text.casefold() or response.id in sampled:
                continue
            skip_reasons[response.id] = (
                "excluded_labelled_evaluation_case: frozen separately"
                if response.id in labelled
                else f"not_selected_for_live_run: sample rule {SAMPLE_RULE_VERSION}"
            )

        if not args.confirm_send:
            print_plan(settings, by_id, absent, sample, skip_reasons)
            return 0

        if not settings.groq_api_key:
            print("GROQ_API_KEY is blank or unavailable.", file=sys.stderr)
            return 1
        live = GroqClassifier(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            max_input_chars=settings.max_input_chars,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            tokens_per_minute=TOKENS_PER_MINUTE,
        )
        router = LiteralAbsenceRouter(live)
        started = time.monotonic()
        analysis = execute_analysis(
            session, dataset.dataset_id, router, settings.max_input_chars, skip_reasons
        )
        duration_seconds = round(time.monotonic() - started, 1)
        attempts = list(
            session.scalars(
                select(ModelAttemptRecord).where(
                    ModelAttemptRecord.analysis_run_id == analysis.analysis_id
                )
            )
        )

    def token_sum(key: str) -> int:
        return sum((a.provider_metadata or {}).get(key) or 0 for a in attempts)

    record = {
        "analysis_id": analysis.analysis_id,
        "status": analysis.status,
        "model": settings.groq_model,
        "prompt_version": analysis.prompt_version,
        "execution_mode": analysis.execution_mode,
        "sample_rule_version": SAMPLE_RULE_VERSION,
        "selected_response_ids": sample,
        "counts": {
            "eligible": analysis.aggregate.eligible,
            "successful": analysis.aggregate.successful,
            "failed": analysis.aggregate.failed,
            "skipped": analysis.aggregate.skipped,
        },
        "prompt_tokens": token_sum("prompt_tokens"),
        "completion_tokens": token_sum("completion_tokens"),
        "duration_seconds": duration_seconds,
        "responses": [
            {"response_id": r.response_id, "status": r.status, "reason": r.reason}
            for r in analysis.results
        ],
    }
    with OUTPUT_PATH.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False)
    print(json.dumps({k: record[k] for k in ("analysis_id", "status", "counts")}, indent=2))
    return 0 if analysis.status == "completed" else 1


def print_plan(settings, by_id, absent, sample, skip_reasons) -> None:
    reason_counts = Counter(reason.split(":")[0] for reason in skip_reasons.values())
    costs = {}
    for response_id in sample:
        payload = build_payload(by_id[response_id].answer_text, settings.groq_model, MAX_OUTPUT_TOKENS)
        costs[response_id] = math.ceil(len(json.dumps(payload).encode("utf-8")) / CHARS_PER_TOKEN)
    total_input = sum(costs.values())
    total_charged = total_input + MAX_OUTPUT_TOKENS * len(sample)
    minutes = total_charged / (0.9 * TOKENS_PER_MINUTE)
    print(f"model: {settings.groq_model}  sample rule: {SAMPLE_RULE_VERSION}")
    print(f"literal absence (rules, no network): {len(absent)}")
    print(f"sampled (groq): {len(sample)}")
    print(f"skipped: {len(skip_reasons)}")
    for reason, count in sorted(reason_counts.items()):
        print(f"  {reason}: {count}")
    for engine in sorted({by_id[i].engine for i in sample}):
        ids = [i for i in sample if by_id[i].engine == engine]
        print(f"sampled {engine} ({len(ids)}):")
        for response_id in ids:
            print(f"  {response_id}  ~{costs[response_id]} input tokens")
    print(f"estimated input tokens total: {total_input}")
    print(f"with {MAX_OUTPUT_TOKENS} reserved output tokens each: {total_charged}")
    print(f"estimated minutes at 0.9*{TOKENS_PER_MINUTE} tokens/min: {minutes:.1f}")


if __name__ == "__main__":
    raise SystemExit(main())
