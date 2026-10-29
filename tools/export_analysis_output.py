#!/usr/bin/env python3
"""Write evaluation/analysis-output.json from a finished analysis.

The database is opened read-only and copied into memory; the report text comes from the real
generator (backend.app.reports._initial_content). Nothing is written to the database and no model
or network is used. An existing output file is not replaced unless --overwrite is given.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend.app.analysis import AnalysisNotFoundError, get_analysis  # noqa: E402
from backend.app.models import ModelAttemptRecord, ResponseClassificationRecord, ResponseRecord  # noqa: E402
from backend.app.reports import _initial_content  # noqa: E402
from tools.check_report_evidence import check_report_evidence  # noqa: E402

LIVE_DATABASE = ROOT / "backend" / "live-run.db"
LIVE_ANALYSIS_ID = "f93000a1-5b97-4146-a72d-6fecb9f1f160"
OUTPUT_PATH = ROOT / "evaluation" / "analysis-output.json"

# Open problems that remain. Earlier review items (D2 evidence, quote cutter, empty quote, remedy 2,
# D3 title, "valid" wording, weak tests) are fixed in code.
KNOWN_ISSUES = [
    {
        "id": 1,
        "issue": (
            "Prompts 026-030 are labelled 'branded' in the frozen prompt-categories-v1 mapping, but "
            "their text does not name Kasparro, so branded name rates cover 25 prompts that name it "
            "and 5 that do not. Diagnostic 2 cites only answers to prompts that name it and says so; "
            "the mapping itself is unchanged."
        ),
    },
    {
        "id": 2,
        "issue": (
            "The freeze tools read the deleted classification.py and no longer run. "
            "tools/benchmark_model.py is not deleted."
        ),
    },
]


class OutputExistsError(FileExistsError):
    pass


def _memory_copy(database_path: Path) -> sqlite3.Connection:
    """Copy the database into memory through a read-only connection."""
    source = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    memory = sqlite3.connect(":memory:", check_same_thread=False)
    try:
        source.backup(memory)
    finally:
        source.close()
    return memory


def build_output(database_path: Path, analysis_id: str) -> dict:
    memory = _memory_copy(database_path)
    engine = create_engine("sqlite://", creator=lambda: memory, poolclass=StaticPool)
    try:
        with Session(engine) as session:
            analysis = get_analysis(session, analysis_id)
            content = _initial_content(session, analysis_id).model_dump(mode="json")
            records = list(
                session.scalars(
                    select(ResponseClassificationRecord).where(
                        ResponseClassificationRecord.analysis_run_id == analysis_id
                    )
                )
            )
            answers = dict(
                session.execute(
                    select(ResponseRecord.id, ResponseRecord.answer_text).where(
                        ResponseRecord.id.in_([record.response_id for record in records])
                    )
                ).all()
            )
            rule_settled = len(
                set(
                    session.scalars(
                        select(ModelAttemptRecord.response_id).where(
                            ModelAttemptRecord.analysis_run_id == analysis_id,
                            ModelAttemptRecord.execution_mode == "rules",
                        )
                    )
                )
            )
    finally:
        engine.dispose()
        memory.close()

    summary = content["summary"]
    calls = summary["model_classification"]["calls"]
    by_response = {
        record.response_id: {"status": record.status, "classification": record.classification}
        for record in records
    }
    return {
        "generated_by": "tools/export_analysis_output.py",
        "source": {"database_file": database_path.name, "analysis_id": analysis_id},
        "run": {
            "status": analysis.status,
            "execution_mode": summary["execution_mode"],
            "model_identifier": summary["model_identifier"],
            "prompt_version": summary["prompt_version"],
            "prompt_mapping_version": summary["prompt_mapping_version"],
            "responses": {
                "eligible": analysis.aggregate.eligible,
                "successful": analysis.aggregate.successful,
                "failed": analysis.aggregate.failed,
                "skipped": analysis.aggregate.skipped,
            },
            "settled_by_literal_rule": rule_settled,
            "model_calls": {
                "attempted": calls["valid"] + calls["failed"],
                "valid": calls["valid"],
                "failed": calls["failed"],
                "quote_rejections": calls["quote_rejections"],
            },
            "score_scope": summary["score_scope"],
        },
        "literal_name_counts": summary["literal_name_counts"],
        "model_classification": summary["model_classification"],
        "diagnostics": content["diagnostics"],
        "remedies": content["remedies"],
        "evidence_check": {
            "checker": "tools/check_report_evidence.py",
            "problems": check_report_evidence(content, by_response, answers),
        },
        "known_issues": KNOWN_ISSUES,
        "active_time": {"hours": None, "note": "owner to supply real hours"},
    }


def write_output(
    database_path: Path, analysis_id: str, output_path: Path = OUTPUT_PATH, overwrite: bool = False
) -> dict:
    if output_path.exists() and not overwrite:
        raise OutputExistsError(f"Refusing to overwrite {output_path}; pass --overwrite to replace it.")
    data = build_output(database_path, analysis_id)
    with output_path.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=LIVE_DATABASE)
    parser.add_argument("--analysis-id", default=LIVE_ANALYSIS_ID)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = write_output(args.database, args.analysis_id, args.output, args.overwrite)
    except (OutputExistsError, AnalysisNotFoundError, sqlite3.Error) as exc:
        print(f"Not written: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}")
    print("top-level keys:", ", ".join(data))
    for diagnostic in data["diagnostics"]:
        print("diagnostic:", diagnostic["title"])
    print("evidence problems:", len(data["evidence_check"]["problems"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
