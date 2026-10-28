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
    execution_mode: Literal["stub", "replay", "local_ollama"] = "stub"
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

