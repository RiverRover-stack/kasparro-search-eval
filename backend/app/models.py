from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    pack_version: Mapped[str] = mapped_column(String(32))
    input_hash: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    prompts: Mapped[list[PromptRecord]] = relationship(back_populates="dataset")
    responses: Mapped[list[ResponseRecord]] = relationship(back_populates="dataset")
    citations: Mapped[list[CitationRecord]] = relationship(back_populates="dataset")
    provenance_records: Mapped[list[ProviderProvenance]] = relationship(back_populates="dataset")
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(back_populates="dataset")


class PromptRecord(Base):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    text: Mapped[str] = mapped_column(Text)
    raw_record: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))

    dataset: Mapped[Dataset] = relationship(back_populates="prompts")


class ResponseRecord(Base):
    __tablename__ = "responses"
    __table_args__ = (UniqueConstraint("prompt_id", "engine", name="uq_prompt_engine"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"), index=True)
    engine: Mapped[str] = mapped_column(String(32), index=True)
    answer_text: Mapped[str] = mapped_column(Text)
    answer_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_record: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))

    dataset: Mapped[Dataset] = relationship(back_populates="responses")


class CitationRecord(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("responses.id"), index=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"), index=True)
    engine: Mapped[str] = mapped_column(String(32), index=True)
    occurrence_order: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text)
    raw_record: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))

    dataset: Mapped[Dataset] = relationship(back_populates="citations")


class ProviderProvenance(Base):
    __tablename__ = "provider_provenance"
    __table_args__ = (UniqueConstraint("dataset_id", "response_id", name="uq_provenance_response"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("responses.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    probe_id: Mapped[str] = mapped_column(String(256), index=True)
    engine: Mapped[str] = mapped_column(String(32), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    raw_record: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))

    dataset: Mapped[Dataset] = relationship(back_populates="provenance_records")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    execution_mode: Mapped[str] = mapped_column(String(32))
    model_identifier: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    eligible_count: Mapped[int] = mapped_column(Integer, default=0)
    successful_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="analysis_runs")
    attempts: Mapped[list[ModelAttemptRecord]] = relationship(back_populates="analysis_run")
    results: Mapped[list[ResponseClassificationRecord]] = relationship(back_populates="analysis_run")
    report: Mapped[Report | None] = relationship(back_populates="analysis_run")


class ModelAttemptRecord(Base):
    __tablename__ = "model_attempts"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "response_id", "attempt_number", name="uq_model_attempt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("responses.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    execution_mode: Mapped[str] = mapped_column(String(32))
    model_identifier: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="attempts")


class ResponseClassificationRecord(Base):
    __tablename__ = "response_classification_results"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "response_id", name="uq_analysis_response"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("responses.id"), index=True)
    prompt_id: Mapped[str] = mapped_column(String(256), index=True)
    engine: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    visibility_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_present: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="results")
    report_evidence_links: Mapped[list[ReportEvidenceLink]] = relationship(
        back_populates="response_result"
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id"), unique=True, index=True
    )
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="report")
    versions: Mapped[list[ReportVersion]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class ReportVersion(Base):
    __tablename__ = "report_versions"
    __table_args__ = (UniqueConstraint("report_id", "version_number", name="uq_report_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    submitted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped[Report] = relationship(back_populates="versions")
    evidence_links: Mapped[list[ReportEvidenceLink]] = relationship(
        back_populates="report_version", cascade="all, delete-orphan"
    )
    decision: Mapped[ReviewDecision | None] = relationship(
        back_populates="report_version", cascade="all, delete-orphan"
    )


class ReportEvidenceLink(Base):
    __tablename__ = "report_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "report_version_id",
            "section_type",
            "section_id",
            "response_result_id",
            name="uq_report_evidence_link",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_version_id: Mapped[str] = mapped_column(ForeignKey("report_versions.id"), index=True)
    section_type: Mapped[str] = mapped_column(String(32))
    section_id: Mapped[str] = mapped_column(String(64))
    response_result_id: Mapped[int] = mapped_column(
        ForeignKey("response_classification_results.id"), index=True
    )

    report_version: Mapped[ReportVersion] = relationship(back_populates="evidence_links")
    response_result: Mapped[ResponseClassificationRecord] = relationship(
        back_populates="report_evidence_links"
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_version_id: Mapped[str] = mapped_column(
        ForeignKey("report_versions.id"), unique=True, index=True
    )
    decision: Mapped[str] = mapped_column(String(16))
    reviewer: Mapped[str] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    report_version: Mapped[ReportVersion] = relationship(back_populates="decision")


class ImportIssue(Base):
    __tablename__ = "import_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    record_type: Mapped[str] = mapped_column(String(32))
    record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    raw_record: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(256))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    contains_credentials: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

