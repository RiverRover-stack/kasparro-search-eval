from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PromptInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ResponseInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    response_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    engine: Literal["aimode", "chatgpt", "gemini"]
    answer_text: str = Field(min_length=1)
    answer_markdown: str | None = None
    capture_status: Literal["captured"]


class CitationInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    citation_id: str = Field(min_length=1)
    response_id: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    engine: Literal["aimode", "chatgpt", "gemini"]
    order: int = Field(ge=1)
    citation_type: Literal["inline_hyperlink", "sources_panel"]
    url: str = Field(min_length=1)


class ImportIssueView(BaseModel):
    record_type: str
    record_id: str | None
    code: str
    message: str


class DatasetImportResponse(BaseModel):
    dataset_id: str
    source_run_id: str
    reused: bool
    accepted: dict[str, int]
    rejected: dict[str, int]
    issues: list[ImportIssueView]
    provenance_records: int = 0


class AnalysisCreateRequest(BaseModel):
    dataset_id: str
    execution_mode: Literal["stub", "replay", "local_ollama", "hosted_groq"] = "stub"
    replay_results: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AnalysisResultView(BaseModel):
    response_id: str
    prompt_id: str
    engine: str
    status: Literal["successful", "failed", "skipped"]
    reason: str | None
    classification: dict[str, Any] | None
    visibility_score: int | None
    citation_present: bool


class AnalysisAggregateView(BaseModel):
    eligible: int
    successful: int
    failed: int
    skipped: int
    average_visibility_score: float | None


class SharedPromptComparisonView(BaseModel):
    shared_successful_prompts: int
    average_score_by_engine: dict[str, float | None]


class AnalysisView(BaseModel):
    analysis_id: str
    dataset_id: str
    status: str
    execution_mode: str
    model_identifier: str
    prompt_version: str
    aggregate: AnalysisAggregateView
    by_engine: dict[str, AnalysisAggregateView]
    by_prompt_branding: dict[str, AnalysisAggregateView]
    prompt_mapping_version: str
    shared_prompt_comparison: SharedPromptComparisonView
    results: list[AnalysisResultView]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ReportDiagnostic(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    observed_pattern: str = Field(min_length=1)
    possible_explanation: str = Field(min_length=1)
    evidence_needed: str = Field(min_length=1)
    uncertainty: Literal["low", "medium", "high"]
    evidence_response_ids: list[str] = Field(min_length=1)


class ReportRemedy(BaseModel):
    id: str = Field(min_length=1)
    priority: int = Field(ge=1, le=3)
    title: str = Field(min_length=1)
    evidence_response_ids: list[str] = Field(min_length=1)
    action: str = Field(min_length=1)
    expected_benefit: str = Field(min_length=1)
    effort: Literal["low", "medium", "high"]
    uncertainty: Literal["low", "medium", "high"]
    validation_step: str = Field(min_length=1)


class ReportContent(BaseModel):
    analysis_id: str
    summary: dict[str, Any]
    diagnostics: list[ReportDiagnostic] = Field(min_length=3, max_length=3)
    remedies: list[ReportRemedy] = Field(min_length=3, max_length=3)


class ReportCreateRequest(BaseModel):
    analysis_id: str


class ReportPatchRequest(BaseModel):
    content: ReportContent


class ReportSubmitRequest(BaseModel):
    version_id: str


class ReportDecisionRequest(BaseModel):
    version_id: str
    decision: Literal["approved", "rejected"]
    comment: str = Field(min_length=1)


class ReviewDecisionView(BaseModel):
    decision: Literal["approved", "rejected"]
    reviewer: str
    comment: str | None
    created_at: str


class ReportVersionView(BaseModel):
    version_id: str
    version_number: int
    status: Literal["draft", "submitted", "approved", "rejected"]
    content_hash: str
    content: ReportContent
    created_by: str
    created_at: str
    submitted_by: str | None
    submitted_at: str | None
    decision: ReviewDecisionView | None


class ReportView(BaseModel):
    report_id: str
    analysis_id: str
    current_version_id: str
    current_version: ReportVersionView
    versions: list[ReportVersionView]


class ReportExportView(BaseModel):
    report_id: str
    analysis_id: str
    version_id: str
    version_number: int
    content_hash: str
    approved_by: str
    approved_at: str
    content: ReportContent

