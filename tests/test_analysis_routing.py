from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.analysis import execute_analysis, get_analysis
from backend.app.classification import (
    ControlledStubClassifier,
    LiteralAbsenceRouter,
    ProviderQuotaExhausted,
)
from backend.app.importer import import_pack
from backend.app.models import AnalysisRun, ResponseRecord
from backend.app.reports import ReportServiceError, create_report
from backend.app.sampling import select_live_sample

ROOT = Path(__file__).resolve().parents[1]


class CountingStub(ControlledStubClassifier):
    def __init__(self, quota_on_call: int | None = None) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.quota_on_call = quota_on_call

    def classify(self, answer_text, response_id=None):
        self.calls.append(response_id)
        if self.quota_on_call == len(self.calls):
            raise ProviderQuotaExhausted("Groq HTTP 429: daily quota")
        return super().classify(answer_text, response_id)


def first_ids(session: Session, count: int) -> list[str]:
    return list(session.scalars(select(ResponseRecord.id).order_by(ResponseRecord.id)))[:count]


def test_skip_reasons_skip_without_calling_classifier(
    session_factory: sessionmaker[Session],
) -> None:
    stub = CountingStub()
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        skipped = first_ids(session, 5)
        analysis = execute_analysis(
            session, dataset.dataset_id, stub, 20_000, {i: "not_selected" for i in skipped}
        )

    assert not set(stub.calls) & set(skipped)
    assert analysis.status == "completed"
    assert analysis.aggregate.skipped == 5
    assert analysis.aggregate.successful == 145
    assert analysis.aggregate.eligible == 150
    assert {r.reason for r in analysis.results if r.status == "skipped"} == {"not_selected"}


def test_quota_exhaustion_interrupts_run_and_blocks_report(
    session_factory: sessionmaker[Session],
) -> None:
    stub = CountingStub(quota_on_call=4)
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        analysis = execute_analysis(session, dataset.dataset_id, stub, 20_000)

        assert analysis.status == "interrupted"
        assert analysis.aggregate.successful == 3
        assert analysis.aggregate.failed == 0
        assert len(analysis.results) == 3
        assert len(stub.calls) == 4
        run = session.get(AnalysisRun, analysis.analysis_id)
        assert run.finished_at is not None
        with pytest.raises(ReportServiceError) as raised:
            create_report(session, analysis.analysis_id, "analyst", "req-1")
        assert raised.value.code == "analysis_not_completed"

        again = execute_analysis(session, dataset.dataset_id, ControlledStubClassifier(), 20_000)
        assert again.status == "completed"


def test_mixed_run_over_real_pack(session_factory: sessionmaker[Session]) -> None:
    stub = CountingStub()
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        responses = list(session.scalars(select(ResponseRecord)))
        sample = set(select_live_sample(responses, set()))
        mentions = {r.id for r in responses if "kasparro" in r.answer_text.casefold()}
        skip_reasons = {i: "not_selected_for_live_run" for i in mentions - sample}
        analysis = execute_analysis(
            session, dataset.dataset_id, LiteralAbsenceRouter(stub), 20_000, skip_reasons
        )

    assert analysis.execution_mode == "rules+stub"
    assert set(stub.calls) == sample
    assert analysis.aggregate.skipped == len(mentions - sample)
    assert analysis.aggregate.failed == 0
    assert analysis.aggregate.successful + analysis.aggregate.skipped == 150
    assert analysis.aggregate.successful == (150 - len(mentions)) + len(sample)
