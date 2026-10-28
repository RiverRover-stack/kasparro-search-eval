from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .analysis import AnalysisBusyError, AnalysisNotFoundError, execute_analysis, get_analysis
from .auth import authenticated_role, require_analyst, require_reviewer
from .classification import (
    ClassificationResult,
    ControlledStubClassifier,
    GroqClassifier,
    OllamaClassifier,
    ReplayClassifier,
)
from .config import Settings
from .database import get_session, initialize_database, mark_interrupted_analyses
from .importer import ImportConflictError, import_pack
from .reports import (
    ReportServiceError,
    create_report,
    decide_report,
    edit_report,
    export_report,
    get_report,
    submit_report,
)
from .schemas import (
    AnalysisCreateRequest,
    AnalysisView,
    DatasetImportResponse,
    ErrorResponse,
    HealthResponse,
    ReportCreateRequest,
    ReportDecisionRequest,
    ReportExportView,
    ReportPatchRequest,
    ReportSubmitRequest,
    ReportView,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    mark_interrupted_analyses()
    yield


app = FastAPI(
    title="Kasparro Visibility Backend",
    version="0.1.0",
    description="Local, evidence-linked AI visibility analysis workflow.",
    lifespan=lifespan,
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(ImportConflictError)
async def import_conflict_handler(request: Request, exc: ImportConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "dataset_conflict",
                "message": str(exc),
                "request_id": request.state.request_id,
                "details": {},
            }
        },
    )


@app.exception_handler(FileNotFoundError)
async def missing_pack_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "input_pack_missing",
                "message": str(exc),
                "request_id": request.state.request_id,
                "details": {},
            }
        },
    )


@app.exception_handler(ReportServiceError)
async def report_error_handler(request: Request, exc: ReportServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": str(exc),
                "request_id": request.state.request_id,
                "details": {},
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    codes = {
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "invalid_request",
        503: "service_unavailable",
    }
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": codes.get(exc.status_code, "http_error"),
                "message": str(exc.detail),
                "request_id": request.state.request_id,
                "details": {},
            }
        },
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(session: Session = Depends(get_session)) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - requires a failed database
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return HealthResponse(status="ok", database="ok")


@app.post(
    "/datasets",
    response_model=DatasetImportResponse,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    tags=["datasets"],
)
def create_dataset(session: Session = Depends(get_session)) -> DatasetImportResponse:
    settings = Settings.from_environment()
    return import_pack(session, settings.input_pack_path)


@app.post(
    "/analyses",
    response_model=AnalysisView,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    tags=["analyses"],
)
def create_analysis(
    payload: AnalysisCreateRequest,
    session: Session = Depends(get_session),
) -> AnalysisView:
    settings = Settings.from_environment()
    if payload.execution_mode == "stub":
        classifier = ControlledStubClassifier()
    elif payload.execution_mode == "replay":
        replay_results = {
            response_id: ClassificationResult.model_validate(result)
            for response_id, result in payload.replay_results.items()
        }
        classifier = ReplayClassifier(replay_results)
    elif payload.execution_mode == "local_ollama":
        classifier = OllamaClassifier(
            max_input_chars=settings.max_input_chars,
            context_tokens=settings.ollama_context_tokens,
        )
    else:
        try:
            classifier = GroqClassifier(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                max_input_chars=settings.max_input_chars,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return execute_analysis(
            session,
            payload.dataset_id,
            classifier,
            settings.max_input_chars,
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnalysisBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisView,
    responses={404: {"model": ErrorResponse}},
    tags=["analyses"],
)
def read_analysis(analysis_id: str, session: Session = Depends(get_session)) -> AnalysisView:
    try:
        return get_analysis(session, analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/reports",
    response_model=ReportView,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    tags=["reports"],
)
def create_report_endpoint(
    payload: ReportCreateRequest,
    request: Request,
    actor: str = Depends(require_analyst),
    session: Session = Depends(get_session),
) -> ReportView:
    return create_report(session, payload.analysis_id, actor, request.state.request_id)


@app.get(
    "/reports/{report_id}",
    response_model=ReportView,
    responses={404: {"model": ErrorResponse}},
    tags=["reports"],
)
def read_report_endpoint(
    report_id: str,
    _role: str = Depends(authenticated_role),
    session: Session = Depends(get_session),
) -> ReportView:
    return get_report(session, report_id)


@app.patch(
    "/reports/{report_id}",
    response_model=ReportView,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    tags=["reports"],
)
def edit_report_endpoint(
    report_id: str,
    payload: ReportPatchRequest,
    request: Request,
    actor: str = Depends(require_analyst),
    session: Session = Depends(get_session),
) -> ReportView:
    return edit_report(session, report_id, payload.content, actor, request.state.request_id)


@app.post(
    "/reports/{report_id}/submit",
    response_model=ReportView,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    tags=["reports"],
)
def submit_report_endpoint(
    report_id: str,
    payload: ReportSubmitRequest,
    request: Request,
    actor: str = Depends(require_analyst),
    session: Session = Depends(get_session),
) -> ReportView:
    return submit_report(
        session, report_id, payload.version_id, actor, request.state.request_id
    )


@app.post(
    "/reports/{report_id}/decision",
    response_model=ReportView,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    tags=["reports"],
)
def decide_report_endpoint(
    report_id: str,
    payload: ReportDecisionRequest,
    request: Request,
    actor: str = Depends(require_reviewer),
    session: Session = Depends(get_session),
) -> ReportView:
    return decide_report(
        session,
        report_id,
        payload.version_id,
        payload.decision,
        payload.comment,
        actor,
        request.state.request_id,
    )


@app.get(
    "/reports/{report_id}/export",
    response_model=ReportExportView,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    tags=["reports"],
)
def export_report_endpoint(
    report_id: str,
    request: Request,
    version_id: str | None = Query(default=None),
    actor: str = Depends(authenticated_role),
    session: Session = Depends(get_session),
) -> ReportExportView:
    return export_report(
        session, report_id, version_id, actor, request.state.request_id
    )

