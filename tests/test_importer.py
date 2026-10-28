from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.importer import ImportConflictError, ImportState, import_pack, validate_records
from backend.app.models import CitationRecord, PromptRecord, ProviderProvenance, ResponseRecord
from backend.app.schemas import PromptInput


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_full_pack_import_is_lossless_and_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        first = import_pack(session, PROJECT_ROOT)
        second = import_pack(session, PROJECT_ROOT)

    assert first.reused is False
    assert first.accepted == {"prompts": 50, "responses": 150, "citations": 2439}
    assert first.rejected == {"prompts": 0, "responses": 0, "citations": 0}
    assert second.reused is True
    assert second.dataset_id == first.dataset_id
    assert first.provenance_records == 150

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PromptRecord)) == 50
        assert session.scalar(select(func.count()).select_from(ResponseRecord)) == 150
        assert session.scalar(select(func.count()).select_from(CitationRecord)) == 2439
        assert session.scalar(select(func.count()).select_from(ProviderProvenance)) == 150


def test_missing_dependency_rejects_response_and_citation(
    session_factory: sessionmaker[Session],
) -> None:
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
        pack_path = Path(directory)
        data = pack_path / "data"
        data.mkdir()
        (pack_path / "PACK_MANIFEST.json").write_text(
            json.dumps({"version": "test"}), encoding="utf-8"
        )
        (data / "run.json").write_text(json.dumps({"run_id": "run-test"}), encoding="utf-8")
        (data / "prompts.jsonl").write_text(
            json.dumps({"prompt_id": "p1", "run_id": "run-test", "text": "Question"}) + "\n",
            encoding="utf-8",
        )
        (data / "responses.jsonl").write_text(
            json.dumps(
                {
                    "response_id": "r1",
                    "run_id": "run-test",
                    "prompt_id": "missing",
                    "engine": "chatgpt",
                    "answer_text": "Answer",
                    "capture_status": "captured",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (data / "citations.jsonl").write_text(
            json.dumps(
                {
                    "citation_id": "c1",
                    "response_id": "r1",
                    "prompt_id": "missing",
                    "engine": "chatgpt",
                    "order": 1,
                    "citation_type": "sources_panel",
                    "url": "https://example.test",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with session_factory() as session:
            result = import_pack(session, pack_path)

    assert result.accepted == {"prompts": 1, "responses": 0, "citations": 0}
    assert result.rejected == {"prompts": 0, "responses": 1, "citations": 1}
    assert [issue.code for issue in result.issues] == ["missing_prompt", "missing_response"]


def test_schema_and_duplicate_ids_are_reported() -> None:
    rows = [
        {"prompt_id": "p1", "run_id": "run", "text": "Question"},
        {"prompt_id": "p1", "run_id": "run", "text": "Question"},
        {"prompt_id": "p1", "run_id": "run", "text": "Changed"},
        {"prompt_id": "p2", "run_id": "run", "text": ""},
    ]
    state = ImportState()

    valid = validate_records(rows, PromptInput, "prompts", "prompt_id", state)

    assert len(valid) == 1
    assert [issue.code for issue in state.issues] == [
        "identical_duplicate",
        "conflicting_id",
        "invalid_schema",
    ]


def test_changed_content_under_existing_run_id_conflicts(
    session_factory: sessionmaker[Session],
) -> None:
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
        pack_path = Path(directory)
        shutil.copy2(PROJECT_ROOT / "PACK_MANIFEST.json", pack_path / "PACK_MANIFEST.json")
        shutil.copytree(PROJECT_ROOT / "data", pack_path / "data")
        shutil.copytree(PROJECT_ROOT / "provenance", pack_path / "provenance")
        with session_factory() as session:
            import_pack(session, pack_path)
            response_path = pack_path / "data" / "responses.jsonl"
            rows = response_path.read_text(encoding="utf-8").splitlines()
            changed = json.loads(rows[0])
            changed["answer_text"] += " changed"
            rows[0] = json.dumps(changed)
            response_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            with pytest.raises(ImportConflictError, match="different input content"):
                import_pack(session, pack_path)


def test_citation_parent_mismatch_is_rejected(
    session_factory: sessionmaker[Session],
) -> None:
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
        pack_path = Path(directory)
        data = pack_path / "data"
        data.mkdir()
        (pack_path / "PACK_MANIFEST.json").write_text('{"version":"test"}', encoding="utf-8")
        (data / "run.json").write_text('{"run_id":"run-test"}', encoding="utf-8")
        (data / "prompts.jsonl").write_text(
            '{"prompt_id":"p1","run_id":"run-test","text":"Question"}\n', encoding="utf-8"
        )
        (data / "responses.jsonl").write_text(
            '{"response_id":"r1","run_id":"run-test","prompt_id":"p1","engine":"chatgpt","answer_text":"Answer","capture_status":"captured"}\n',
            encoding="utf-8",
        )
        (data / "citations.jsonl").write_text(
            '{"citation_id":"c1","response_id":"r1","prompt_id":"p1","engine":"gemini","order":1,"citation_type":"sources_panel","url":"https://example.test"}\n',
            encoding="utf-8",
        )
        with session_factory() as session:
            result = import_pack(session, pack_path)

    assert result.accepted == {"prompts": 1, "responses": 1, "citations": 0}
    assert result.rejected["citations"] == 1
    assert result.issues[0].code == "parent_mismatch"

