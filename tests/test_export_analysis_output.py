from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.analysis import execute_analysis
from backend.app.classification import ControlledStubClassifier
from backend.app.classification.adapters import LiteralAbsenceRouter
from backend.app.database import build_engine, build_session_factory, initialize_database
from backend.app.importer import import_pack
from backend.app.models import ResponseRecord
from tools.export_analysis_output import main, write_output

ROOT = Path(__file__).resolve().parents[1]
QUOTE_FAILURE = (
    "Groq HTTP 400: jsonschema: '/supporting_excerpts/1/quote' does not validate with enum"
)
TOP_LEVEL_KEYS = {
    "generated_by", "source", "run", "literal_name_counts", "model_classification",
    "diagnostics", "remedies", "evidence_check", "known_issues", "active_time",
}


@pytest.fixture
def fixture_db(tmp_path: Path):
    """A file database holding one finished analysis: rule for absent answers, two failed model calls."""
    path = tmp_path / "fixture.db"
    engine = build_engine(f"sqlite:///{path.as_posix()}")
    initialize_database(engine)
    with build_session_factory(engine)() as session:
        dataset = import_pack(session, ROOT)
        named = [
            response.id
            for response in session.scalars(select(ResponseRecord).order_by(ResponseRecord.id))
            if "kasparro" in response.answer_text.casefold()
        ]
        failing = {response_id: QUOTE_FAILURE for response_id in named[:2]}
        router = LiteralAbsenceRouter(ControlledStubClassifier(failures=failing))
        analysis = execute_analysis(session, dataset.dataset_id, router, 20_000)
    engine.dispose()
    return path, analysis.analysis_id


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_output_has_the_expected_parts(fixture_db, tmp_path: Path) -> None:
    database, analysis_id = fixture_db
    output = tmp_path / "out.json"

    assert main(["--database", str(database), "--analysis-id", analysis_id, "--output", str(output)]) == 0

    data = json.loads(output.read_text(encoding="utf-8"))
    assert set(data) == TOP_LEVEL_KEYS
    assert len(data["diagnostics"]) == 3 and len(data["remedies"]) == 3
    assert data["run"]["responses"]["eligible"] == 150
    counts = data["run"]["responses"]
    assert counts["successful"] + counts["failed"] + counts["skipped"] == 150
    assert data["model_classification"]["calls"]["failed"] == 2
    assert data["evidence_check"]["problems"] == []
    assert data["known_issues"]
    assert data["active_time"]["hours"] is None
    assert "owner to supply real hours" in data["active_time"]["note"]


def test_output_never_holds_a_blended_average(fixture_db, tmp_path: Path) -> None:
    database, analysis_id = fixture_db
    output = tmp_path / "out.json"
    write_output(database, analysis_id, output)

    def keys(value) -> list[str]:
        if isinstance(value, dict):
            return list(value) + [k for v in value.values() for k in keys(v)]
        if isinstance(value, list):
            return [k for v in value for k in keys(v)]
        return []

    data = json.loads(output.read_text(encoding="utf-8"))
    assert not [key for key in keys(data) if "average" in key]


def test_database_is_left_untouched(fixture_db, tmp_path: Path) -> None:
    database, analysis_id = fixture_db
    before = _sha256(database)

    write_output(database, analysis_id, tmp_path / "out.json")

    assert _sha256(database) == before
    assert not list(database.parent.glob("fixture.db-*"))


def test_existing_output_is_not_overwritten_without_the_flag(fixture_db, tmp_path: Path) -> None:
    database, analysis_id = fixture_db
    output = tmp_path / "out.json"
    output.write_text("keep me", encoding="utf-8")

    assert main(["--database", str(database), "--analysis-id", analysis_id, "--output", str(output)]) == 1
    assert output.read_text(encoding="utf-8") == "keep me"

    assert main(
        ["--database", str(database), "--analysis-id", analysis_id, "--output", str(output), "--overwrite"]
    ) == 0
    assert set(json.loads(output.read_text(encoding="utf-8"))) == TOP_LEVEL_KEYS


def test_output_is_deterministic(fixture_db, tmp_path: Path) -> None:
    database, analysis_id = fixture_db
    write_output(database, analysis_id, tmp_path / "a.json")
    write_output(database, analysis_id, tmp_path / "b.json")

    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def test_unknown_analysis_or_missing_database_is_a_clean_failure(fixture_db, tmp_path: Path) -> None:
    database, _ = fixture_db
    output = tmp_path / "out.json"

    assert main(["--database", str(database), "--analysis-id", "nope", "--output", str(output)]) == 1
    assert main(
        ["--database", str(tmp_path / "missing.db"), "--analysis-id", "nope", "--output", str(output)]
    ) == 1
    assert not output.exists()
