from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    CitationRecord,
    Dataset,
    ImportIssue,
    PromptRecord,
    ProviderProvenance,
    ResponseRecord,
)
from .schemas import CitationInput, DatasetImportResponse, ImportIssueView, PromptInput, ResponseInput


T = TypeVar("T", bound=BaseModel)
SOURCE_FILES = (
    "data/run.json",
    "data/prompts.jsonl",
    "data/responses.jsonl",
    "data/citations.jsonl",
)
PROVENANCE_FILE = "provenance/provider_payloads.jsonl"


class ImportConflictError(RuntimeError):
    pass


@dataclass
class ParsedRecord:
    value: BaseModel
    raw: dict[str, Any]


@dataclass
class ImportState:
    accepted: dict[str, int] = field(
        default_factory=lambda: {"prompts": 0, "responses": 0, "citations": 0}
    )
    rejected: dict[str, int] = field(
        default_factory=lambda: {"prompts": 0, "responses": 0, "citations": 0}
    )
    issues: list[ImportIssueView] = field(default_factory=list)

    def reject(
        self,
        record_type: str,
        record_id: str | None,
        code: str,
        message: str,
    ) -> None:
        self.rejected[record_type] += 1
        self.issues.append(
            ImportIssueView(
                record_type=record_type,
                record_id=record_id,
                code=code,
                message=message,
            )
        )


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def pack_hash(pack_path: Path) -> str:
    digest = hashlib.sha256()
    for relative_path in SOURCE_FILES:
        path = pack_path / relative_path
        digest.update(relative_path.encode("utf-8"))
        digest.update(path.read_bytes())
    provenance_path = pack_path / PROVENANCE_FILE
    if provenance_path.is_file():
        digest.update(PROVENANCE_FILE.encode("utf-8"))
        digest.update(provenance_path.read_bytes())
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            records.append({"__parse_error__": f"line {line_number}: {exc.msg}"})
            continue
        if not isinstance(record, dict):
            records.append({"__parse_error__": f"line {line_number}: expected an object"})
            continue
        records.append(record)
    return records


def validate_records(
    rows: list[dict[str, Any]],
    schema: type[T],
    record_type: str,
    id_field: str,
    state: ImportState,
) -> list[ParsedRecord]:
    valid: list[ParsedRecord] = []
    seen: dict[str, str] = {}
    for row in rows:
        record_id = row.get(id_field)
        if "__parse_error__" in row:
            state.reject(record_type, None, "invalid_json", row["__parse_error__"])
            continue
        try:
            value = schema.model_validate(row)
        except ValidationError as exc:
            state.reject(record_type, str(record_id) if record_id else None, "invalid_schema", str(exc))
            continue
        fingerprint = canonical_hash(row)
        typed_id = str(getattr(value, id_field))
        if typed_id in seen:
            code = "identical_duplicate" if seen[typed_id] == fingerprint else "conflicting_id"
            state.reject(record_type, typed_id, code, f"Duplicate {id_field} in input")
            continue
        seen[typed_id] = fingerprint
        valid.append(ParsedRecord(value=value, raw=row))
    return valid


def import_pack(session: Session, pack_path: Path) -> DatasetImportResponse:
    pack_path = pack_path.resolve()
    run_path = pack_path / "data" / "run.json"
    manifest_path = pack_path / "PACK_MANIFEST.json"
    if not run_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Configured input pack is missing run.json or PACK_MANIFEST.json")

    run = json.loads(run_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_run_id = str(run["run_id"])
    input_hash = pack_hash(pack_path)
    existing = session.scalar(select(Dataset).where(Dataset.source_run_id == source_run_id))
    if existing:
        if existing.input_hash != input_hash:
            raise ImportConflictError(
                f"Run {source_run_id} already exists with different input content"
            )
        counts = {
            "prompts": len(existing.prompts),
            "responses": len(existing.responses),
            "citations": len(existing.citations),
        }
        return DatasetImportResponse(
            dataset_id=existing.id,
            source_run_id=source_run_id,
            reused=True,
            accepted=counts,
            rejected={"prompts": 0, "responses": 0, "citations": 0},
            issues=[],
            provenance_records=len(existing.provenance_records),
        )

    dataset = Dataset(
        id=str(uuid4()),
        source_run_id=source_run_id,
        pack_version=str(manifest["version"]),
        input_hash=input_hash,
    )
    session.add(dataset)
    session.flush()
    state = ImportState()

    prompt_rows = validate_records(
        read_jsonl(pack_path / "data" / "prompts.jsonl"),
        PromptInput,
        "prompts",
        "prompt_id",
        state,
    )
    response_rows = validate_records(
        read_jsonl(pack_path / "data" / "responses.jsonl"),
        ResponseInput,
        "responses",
        "response_id",
        state,
    )
    citation_rows = validate_records(
        read_jsonl(pack_path / "data" / "citations.jsonl"),
        CitationInput,
        "citations",
        "citation_id",
        state,
    )

    prompt_ids: set[str] = set()
    for parsed in prompt_rows:
        value = parsed.value
        assert isinstance(value, PromptInput)
        if value.run_id != source_run_id:
            state.reject("prompts", value.prompt_id, "run_mismatch", "Prompt run_id does not match data/run.json")
            continue
        session.add(
            PromptRecord(
                id=value.prompt_id,
                dataset_id=dataset.id,
                run_id=value.run_id,
                text=value.text,
                raw_record=parsed.raw,
                content_hash=canonical_hash(parsed.raw),
            )
        )
        prompt_ids.add(value.prompt_id)
        state.accepted["prompts"] += 1

    response_by_id: dict[str, ResponseInput] = {}
    prompt_engine_pairs: set[tuple[str, str]] = set()
    for parsed in response_rows:
        value = parsed.value
        assert isinstance(value, ResponseInput)
        if value.run_id != source_run_id:
            state.reject("responses", value.response_id, "run_mismatch", "Response run_id does not match data/run.json")
            continue
        if value.prompt_id not in prompt_ids:
            state.reject("responses", value.response_id, "missing_prompt", f"Unknown prompt_id {value.prompt_id}")
            continue
        pair = (value.prompt_id, value.engine)
        if pair in prompt_engine_pairs:
            state.reject("responses", value.response_id, "duplicate_prompt_engine", "Prompt and engine pair must be unique")
            continue
        prompt_engine_pairs.add(pair)
        session.add(
            ResponseRecord(
                id=value.response_id,
                dataset_id=dataset.id,
                run_id=value.run_id,
                prompt_id=value.prompt_id,
                engine=value.engine,
                answer_text=value.answer_text,
                answer_markdown=value.answer_markdown,
                raw_record=parsed.raw,
                content_hash=canonical_hash(parsed.raw),
            )
        )
        response_by_id[value.response_id] = value
        state.accepted["responses"] += 1

    for parsed in citation_rows:
        value = parsed.value
        assert isinstance(value, CitationInput)
        parent = response_by_id.get(value.response_id)
        if parent is None:
            state.reject("citations", value.citation_id, "missing_response", f"Unknown response_id {value.response_id}")
            continue
        if value.prompt_id != parent.prompt_id or value.engine != parent.engine:
            state.reject(
                "citations",
                value.citation_id,
                "parent_mismatch",
                "Citation prompt_id or engine does not match its response",
            )
            continue
        session.add(
            CitationRecord(
                id=value.citation_id,
                dataset_id=dataset.id,
                response_id=value.response_id,
                prompt_id=value.prompt_id,
                engine=value.engine,
                occurrence_order=value.order,
                url=value.url,
                raw_record=parsed.raw,
                content_hash=canonical_hash(parsed.raw),
            )
        )
        state.accepted["citations"] += 1

    provenance_count = 0
    provenance_path = pack_path / PROVENANCE_FILE
    provenance_rows = read_jsonl(provenance_path) if provenance_path.is_file() else []
    for line_number, raw in enumerate(provenance_rows, start=1):
        response_id = str(raw.get("response_id", ""))
        parent = response_by_id.get(response_id)
        required = ("run_id", "response_id", "probe_id", "engine", "prompt", "raw_provider_response")
        if "__parse_error__" in raw or any(key not in raw for key in required):
            state.issues.append(
                ImportIssueView(
                    record_type="provenance",
                    record_id=response_id or None,
                    code="invalid_provenance",
                    message=f"Invalid provider provenance at line {line_number}",
                )
            )
            continue
        if parent is None:
            state.issues.append(
                ImportIssueView(
                    record_type="provenance",
                    record_id=response_id,
                    code="missing_response",
                    message=f"Unknown response_id {response_id}",
                )
            )
            continue
        if (
            str(raw["run_id"]) != source_run_id
            or str(raw["engine"]) != parent.engine
            or str(raw["probe_id"]) != parent.prompt_id
        ):
            state.issues.append(
                ImportIssueView(
                    record_type="provenance",
                    record_id=response_id,
                    code="parent_mismatch",
                    message="Provider provenance run, prompt, or engine does not match its response",
                )
            )
            continue
        session.add(
            ProviderProvenance(
                dataset_id=dataset.id,
                response_id=response_id,
                run_id=str(raw["run_id"]),
                probe_id=str(raw["probe_id"]),
                engine=str(raw["engine"]),
                prompt=str(raw["prompt"]),
                raw_record=raw,
                content_hash=canonical_hash(raw),
            )
        )
        provenance_count += 1

    for issue in state.issues:
        session.add(
            ImportIssue(
                dataset_id=dataset.id,
                record_type=issue.record_type,
                record_id=issue.record_id,
                code=issue.code,
                message=issue.message,
                raw_record=None,
            )
        )
    session.commit()
    return DatasetImportResponse(
        dataset_id=dataset.id,
        source_run_id=source_run_id,
        reused=False,
        accepted=state.accepted,
        rejected=state.rejected,
        issues=state.issues,
        provenance_records=provenance_count,
    )

