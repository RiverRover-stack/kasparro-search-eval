from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.analysis import execute_analysis
from backend.app.auth import require_reviewer
from backend.app.classification import ControlledStubClassifier
from backend.app.importer import import_pack
from backend.app.main import app
from backend.app.models import AuditEvent, ReportEvidenceLink, ReportVersion, ReviewDecision
from backend.app.reports import (
    ReportServiceError,
    create_report,
    decide_report,
    edit_report,
    export_report,
    get_report,
    submit_report,
)


ROOT = Path(__file__).resolve().parents[1]


def test_report_endpoints_are_exposed_in_openapi() -> None:
    paths = app.openapi()["paths"]
    assert "post" in paths["/reports"]
    assert {"get", "patch"}.issubset(paths["/reports/{report_id}"])
    assert "post" in paths["/reports/{report_id}/submit"]
    assert "post" in paths["/reports/{report_id}/decision"]
    assert "get" in paths["/reports/{report_id}/export"]


def test_report_lifecycle_authorization_immutability_and_versioned_export(
    session_factory: sessionmaker[Session], monkeypatch
) -> None:
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        analysis = execute_analysis(session, dataset.dataset_id, ControlledStubClassifier(), 20_000)
        report = create_report(session, analysis.analysis_id, "analyst", "request-create")
        report_id = report.report_id
        version_1 = report.current_version_id
        content_1 = deepcopy(report.current_version.content)
        hash_1 = report.current_version.content_hash
        assert len(content_1.diagnostics) == 3
        assert len(content_1.remedies) == 3

        with pytest.raises(HTTPException) as wrong_role:
            require_reviewer("analyst")
        assert wrong_role.value.status_code == 403

        submitted = submit_report(
            session, report_id, version_1, "analyst", "request-submit"
        )
        assert submitted.current_version.status == "submitted"

        approved = decide_report(
            session,
            report_id,
            version_1,
            "approved",
            "Evidence reviewed.",
            "reviewer",
            "request-approve",
        )
        assert approved.current_version.status == "approved"

        exported = export_report(
            session, report_id, None, "analyst", "request-export-v1"
        )
        assert exported.version_id == version_1
        assert exported.content_hash == hash_1

        content_2 = content_1.model_copy(deep=True)
        content_2.diagnostics[0].observed_pattern = (
            "Analyst correction: coverage is retained, and the narrative needs fresh review."
        )
        edited = edit_report(
            session, report_id, content_2, "analyst", "request-edit"
        )
        version_2 = edited.current_version_id
        assert version_2 != version_1
        assert edited.current_version.status == "draft"
        frozen_v1 = next(
            version for version in edited.versions if version.version_id == version_1
        )
        assert frozen_v1.status == "approved"
        assert frozen_v1.content == content_1
        assert frozen_v1.content_hash == hash_1

        with pytest.raises(ReportServiceError) as default_export:
            export_report(session, report_id, None, "analyst", "request-default-export")
        assert default_export.value.code == "version_not_approved"
        old_export = export_report(
            session, report_id, version_1, "analyst", "request-old-export"
        )
        assert old_export.version_id == version_1

        with pytest.raises(ReportServiceError) as stale_approval:
            decide_report(
                session,
                report_id,
                version_2,
                "approved",
                None,
                "reviewer",
                "request-stale",
            )
        assert stale_approval.value.code == "version_not_submitted"
        with pytest.raises(ReportServiceError):
            export_report(session, report_id, version_2, "analyst", "request-v2-export")

        submit_report(session, report_id, version_2, "analyst", "request-submit-v2")
        rejected = decide_report(
            session,
            report_id,
            version_2,
            "rejected",
            "Narrative correction needs evidence.",
            "reviewer",
            "request-reject",
        )
        assert rejected.current_version.status == "rejected"
        with pytest.raises(ReportServiceError):
            export_report(session, report_id, version_2, "analyst", "request-rejected")

        retrieved = get_report(session, report_id)
        assert retrieved.current_version.content == content_2
        assert session.scalar(select(func.count()).select_from(ReportVersion)) == 2
        assert session.scalar(select(func.count()).select_from(ReviewDecision)) == 2
        assert session.scalar(select(func.count()).select_from(ReportEvidenceLink)) > 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) >= 7


def test_report_rejects_foreign_evidence_reference(
    session_factory: sessionmaker[Session], monkeypatch
) -> None:
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        analysis = execute_analysis(session, dataset.dataset_id, ControlledStubClassifier(), 20_000)
        report = create_report(session, analysis.analysis_id, "analyst", "request-create")
        content = report.current_version.content.model_copy(deep=True)
        content.diagnostics[0].evidence_response_ids = ["not-from-this-analysis"]
        with pytest.raises(ReportServiceError) as caught:
            edit_report(session, report.report_id, content, "analyst", "request-edit")
        assert caught.value.status_code == 422
        assert caught.value.code == "invalid_evidence_reference"
