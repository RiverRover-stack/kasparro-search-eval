from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis import get_analysis, prompt_branding_labels
from .findings import BRAND, build_findings
from .models import (
    AnalysisRun,
    AuditEvent,
    ModelAttemptRecord,
    Report,
    ReportEvidenceLink,
    ReportVersion,
    ResponseClassificationRecord,
    PromptRecord,
    ResponseRecord,
    ReviewDecision,
    utc_now,
)
from .schemas import (
    ReportContent,
    ReportExportView,
    ReportVersionView,
    ReportView,
    ReviewDecisionView,
)


class ReportServiceError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _content_hash(content: dict) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _audit(
    session: Session,
    request_id: str,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            request_id=request_id,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            contains_credentials=False,
        )
    )


def _result_records(session: Session, analysis_id: str) -> list[ResponseClassificationRecord]:
    return list(
        session.scalars(
            select(ResponseClassificationRecord)
            .where(ResponseClassificationRecord.analysis_run_id == analysis_id)
            .order_by(ResponseClassificationRecord.id)
        )
    )


def _initial_content(session: Session, analysis_id: str) -> ReportContent:
    analysis = get_analysis(session, analysis_id)
    records = _result_records(session, analysis_id)
    if not records:
        raise ReportServiceError(409, "analysis_has_no_results", "Analysis has no persisted results")
    answers = {
        response_id: answer_text
        for response_id, answer_text in session.execute(
            select(ResponseRecord.id, ResponseRecord.answer_text).where(
                ResponseRecord.id.in_([record.response_id for record in records])
            )
        )
    }
    rule_response_ids = set(
        session.scalars(
            select(ModelAttemptRecord.response_id).where(
                ModelAttemptRecord.analysis_run_id == analysis_id,
                ModelAttemptRecord.execution_mode == "rules",
            )
        )
    )
    prompt_named = {
        prompt_id
        for prompt_id, text in session.execute(
            select(PromptRecord.id, PromptRecord.text).where(
                PromptRecord.id.in_({record.prompt_id for record in records})
            )
        )
        if BRAND in text.casefold()
    }
    _, labels = prompt_branding_labels(session.get(AnalysisRun, analysis_id).dataset.source_run_id)
    try:
        blocks, diagnostics, remedies = build_findings(
            records, answers, labels, rule_response_ids, analysis.execution_mode, prompt_named
        )
    except ValueError as exc:
        raise ReportServiceError(409, "analysis_not_reportable", str(exc)) from exc
    return ReportContent(
        analysis_id=analysis_id,
        summary={
            "execution_mode": analysis.execution_mode,
            "model_identifier": analysis.model_identifier,
            "prompt_version": analysis.prompt_version,
            "prompt_mapping_version": analysis.prompt_mapping_version,
            **blocks,
            "score_scope": "Visibility and endorsement only; not factual accuracy or business impact.",
        },
        diagnostics=diagnostics,
        remedies=remedies,
    )


def _validate_and_link_evidence(
    session: Session,
    report: Report,
    version: ReportVersion,
    content: ReportContent,
) -> None:
    if content.analysis_id != report.analysis_run_id:
        raise ReportServiceError(
            422, "analysis_mismatch", "Report content must retain its original analysis ID"
        )
    diagnostic_ids = [item.id for item in content.diagnostics]
    remedy_ids = [item.id for item in content.remedies]
    if len(set(diagnostic_ids)) != 3 or len(set(remedy_ids)) != 3:
        raise ReportServiceError(422, "duplicate_section_id", "Report section IDs must be unique")
    if sorted(item.priority for item in content.remedies) != [1, 2, 3]:
        raise ReportServiceError(422, "invalid_priorities", "Remedy priorities must be 1, 2, and 3")

    records = _result_records(session, report.analysis_run_id)
    by_response = {record.response_id: record for record in records}
    sections = [
        ("diagnostic", item.id, item.evidence_response_ids) for item in content.diagnostics
    ] + [("remedy", item.id, item.evidence_response_ids) for item in content.remedies]
    for section_type, section_id, response_ids in sections:
        for response_id in dict.fromkeys(response_ids):
            record = by_response.get(response_id)
            if record is None:
                raise ReportServiceError(
                    422,
                    "invalid_evidence_reference",
                    f"Evidence response {response_id} does not belong to analysis {report.analysis_run_id}",
                )
            session.add(
                ReportEvidenceLink(
                    report_version_id=version.id,
                    section_type=section_type,
                    section_id=section_id,
                    response_result_id=record.id,
                )
            )


def _decision_view(decision: ReviewDecision | None) -> ReviewDecisionView | None:
    if decision is None:
        return None
    return ReviewDecisionView(
        decision=decision.decision,
        reviewer=decision.reviewer,
        comment=decision.comment,
        created_at=_iso(decision.created_at),
    )


def _version_view(version: ReportVersion) -> ReportVersionView:
    return ReportVersionView(
        version_id=version.id,
        version_number=version.version_number,
        status=version.status,
        content_hash=version.content_hash,
        content=ReportContent.model_validate(version.content),
        created_by=version.created_by,
        created_at=_iso(version.created_at),
        submitted_by=version.submitted_by,
        submitted_at=_iso(version.submitted_at),
        decision=_decision_view(version.decision),
    )


def get_report(session: Session, report_id: str) -> ReportView:
    report = session.get(Report, report_id)
    if report is None:
        raise ReportServiceError(404, "report_not_found", f"Report {report_id} was not found")
    versions = list(
        session.scalars(
            select(ReportVersion)
            .where(ReportVersion.report_id == report.id)
            .order_by(ReportVersion.version_number)
        )
    )
    current = next((version for version in versions if version.id == report.current_version_id), None)
    if current is None:
        raise ReportServiceError(500, "report_state_invalid", "Current report version is missing")
    return ReportView(
        report_id=report.id,
        analysis_id=report.analysis_run_id,
        current_version_id=current.id,
        current_version=_version_view(current),
        versions=[_version_view(version) for version in versions],
    )


def create_report(
    session: Session, analysis_id: str, actor: str, request_id: str
) -> ReportView:
    analysis = session.get(AnalysisRun, analysis_id)
    if analysis is None:
        raise ReportServiceError(404, "analysis_not_found", f"Analysis {analysis_id} was not found")
    if analysis.status != "completed":
        raise ReportServiceError(409, "analysis_not_completed", "Only completed analyses can be reported")
    existing = session.scalar(select(Report).where(Report.analysis_run_id == analysis_id))
    if existing is not None:
        raise ReportServiceError(409, "report_exists", "A report already exists for this analysis")

    content = _initial_content(session, analysis_id)
    content_data = content.model_dump(mode="json")
    report = Report(
        id=str(uuid4()), analysis_run_id=analysis_id, created_by=actor, current_version_id=None
    )
    version = ReportVersion(
        id=str(uuid4()),
        report_id=report.id,
        version_number=1,
        status="draft",
        content=content_data,
        content_hash=_content_hash(content_data),
        created_by=actor,
    )
    report.current_version_id = version.id
    session.add_all([report, version])
    session.flush()
    _validate_and_link_evidence(session, report, version, content)
    _audit(session, request_id, actor, "report.created", "report", report.id, {"version_id": version.id})
    session.commit()
    return get_report(session, report.id)


def edit_report(
    session: Session,
    report_id: str,
    content: ReportContent,
    actor: str,
    request_id: str,
) -> ReportView:
    report = session.get(Report, report_id)
    if report is None:
        raise ReportServiceError(404, "report_not_found", f"Report {report_id} was not found")
    original = session.scalar(
        select(ReportVersion)
        .where(ReportVersion.report_id == report_id)
        .order_by(ReportVersion.version_number)
        .limit(1)
    )
    if original is None:
        raise ReportServiceError(500, "report_state_invalid", "Original report version is missing")
    if content.summary != original.content.get("summary"):
        raise ReportServiceError(
            422, "computed_summary_immutable", "Computed report summary cannot be edited"
        )
    next_number = (session.scalar(select(func.max(ReportVersion.version_number)).where(ReportVersion.report_id == report.id)) or 0) + 1
    content_data = content.model_dump(mode="json")
    version = ReportVersion(
        id=str(uuid4()),
        report_id=report.id,
        version_number=next_number,
        status="draft",
        content=content_data,
        content_hash=_content_hash(content_data),
        created_by=actor,
    )
    session.add(version)
    session.flush()
    _validate_and_link_evidence(session, report, version, content)
    report.current_version_id = version.id
    _audit(session, request_id, actor, "report.edited", "report", report.id, {"version_id": version.id})
    session.commit()
    return get_report(session, report.id)


def submit_report(
    session: Session, report_id: str, version_id: str, actor: str, request_id: str
) -> ReportView:
    report = session.get(Report, report_id)
    if report is None:
        raise ReportServiceError(404, "report_not_found", f"Report {report_id} was not found")
    if version_id != report.current_version_id:
        raise ReportServiceError(409, "stale_report_version", "Only the current report version can be submitted")
    version = session.get(ReportVersion, version_id)
    if version is None or version.report_id != report.id:
        raise ReportServiceError(404, "version_not_found", f"Version {version_id} was not found")
    if version.status != "draft":
        raise ReportServiceError(409, "version_not_draft", "Only a draft version can be submitted")
    version.status = "submitted"
    version.submitted_by = actor
    version.submitted_at = utc_now()
    _audit(session, request_id, actor, "report.submitted", "report_version", version.id)
    session.commit()
    return get_report(session, report.id)


def decide_report(
    session: Session,
    report_id: str,
    version_id: str,
    decision: str,
    comment: str | None,
    actor: str,
    request_id: str,
) -> ReportView:
    report = session.get(Report, report_id)
    if report is None:
        raise ReportServiceError(404, "report_not_found", f"Report {report_id} was not found")
    version = session.get(ReportVersion, version_id)
    if version is None or version.report_id != report.id:
        raise ReportServiceError(404, "version_not_found", f"Version {version_id} was not found")
    if version.status != "submitted":
        raise ReportServiceError(409, "version_not_submitted", "Only a submitted version can be decided")
    if version.id != report.current_version_id:
        raise ReportServiceError(409, "stale_report_version", "Only the current report version can be decided")
    if decision not in {"approved", "rejected"}:
        raise ReportServiceError(422, "invalid_decision", "Decision must be approved or rejected")
    if not comment or not comment.strip():
        raise ReportServiceError(422, "comment_required", "A reviewer comment is required")
    version.status = decision
    version.decision = ReviewDecision(
        report_version_id=version.id,
        decision=decision,
        reviewer=actor,
        comment=comment,
    )
    _audit(
        session,
        request_id,
        actor,
        f"report.{decision}",
        "report_version",
        version.id,
        {"comment_present": bool(comment)},
    )
    session.commit()
    return get_report(session, report.id)


def export_report(
    session: Session,
    report_id: str,
    version_id: str | None,
    actor: str,
    request_id: str,
) -> ReportExportView:
    report = session.get(Report, report_id)
    if report is None:
        raise ReportServiceError(404, "report_not_found", f"Report {report_id} was not found")
    selected_id = version_id or report.current_version_id
    version = session.get(ReportVersion, selected_id)
    if version is None or version.report_id != report.id:
        raise ReportServiceError(404, "version_not_found", f"Version {selected_id} was not found")
    if version.status != "approved" or version.decision is None or version.decision.decision != "approved":
        raise ReportServiceError(409, "version_not_approved", "Only an approved report version can be exported")
    _audit(session, request_id, actor, "report.exported", "report_version", version.id)
    session.commit()
    return ReportExportView(
        report_id=report.id,
        analysis_id=report.analysis_run_id,
        version_id=version.id,
        version_number=version.version_number,
        content_hash=version.content_hash,
        approved_by=version.decision.reviewer,
        approved_at=_iso(version.decision.created_at),
        content=ReportContent.model_validate(version.content),
    )
