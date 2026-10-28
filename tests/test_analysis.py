from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.analysis import execute_analysis, get_analysis
from backend.app.classification import ControlledStubClassifier
from backend.app.importer import import_pack
from backend.app.models import ModelAttemptRecord, ResponseClassificationRecord
from backend.app.main import create_analysis, read_analysis
from backend.app.schemas import AnalysisCreateRequest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_stub_analysis_persists_terminal_results_and_aggregates(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        created = execute_analysis(session, dataset.dataset_id, ControlledStubClassifier(), 20_000)
        fetched = get_analysis(session, created.analysis_id)

        assert fetched.status == "completed"
        assert fetched.aggregate.eligible == 150
        assert fetched.aggregate.successful == 150
        assert fetched.aggregate.failed == 0
        assert fetched.aggregate.skipped == 0
        assert fetched.shared_prompt_comparison.shared_successful_prompts == 50
        assert session.scalar(select(func.count()).select_from(ModelAttemptRecord)) == 150
        assert session.scalar(select(func.count()).select_from(ResponseClassificationRecord)) == 150


def test_partial_failure_and_oversized_input_keep_valid_results(
    session_factory: sessionmaker[Session],
) -> None:
    failure_id = "a3fdd8bb-bcd9-4608-9786-ad4b3a2c7dc2"
    classifier = ControlledStubClassifier({failure_id: "TimeoutError: controlled timeout"})
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        analysis = execute_analysis(session, dataset.dataset_id, classifier, 10_000)

    statuses = {result.response_id: result for result in analysis.results}
    assert statuses[failure_id].status == "failed"
    assert "controlled timeout" in (statuses[failure_id].reason or "")
    largest = statuses["0f38b477-9f3c-44a8-9d10-0b6016db6150"]
    assert largest.status == "skipped"
    assert "oversized_input" in (largest.reason or "")
    assert analysis.aggregate.successful > 0
    assert analysis.aggregate.failed == 1
    assert analysis.aggregate.skipped >= 1
    assert analysis.aggregate.eligible == 150


def test_analysis_endpoint_functions_support_stub_and_persisted_get(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        created = create_analysis(
            AnalysisCreateRequest(dataset_id=dataset.dataset_id, execution_mode="stub"),
            session,
        )
        fetched = read_analysis(created.analysis_id, session)

    assert fetched.analysis_id == created.analysis_id
    assert fetched.execution_mode == "stub"
    assert fetched.aggregate == created.aggregate


def test_replay_endpoint_records_missing_replay_items_as_failures(
    session_factory: sessionmaker[Session],
) -> None:
    response_id = "a3fdd8bb-bcd9-4608-9786-ad4b3a2c7dc2"
    replay_result = {
        "contract_version": "classification-v1",
        "brand_mentioned": True,
        "recommended": False,
        "negative_characterization": True,
        "competitors": [],
        "observable_position": None,
        "supporting_excerpts": [
            {
                "kind": "negative_characterization",
                "quote": "Kasparro is not a widely recognized, top-tier agency or tool in the AI visibility space",
            }
        ],
        "uncertainty": "low",
        "uncertainty_reason": "Frozen replay fixture.",
    }
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        analysis = create_analysis(
            AnalysisCreateRequest(
                dataset_id=dataset.dataset_id,
                execution_mode="replay",
                replay_results={response_id: replay_result},
            ),
            session,
        )

    assert analysis.execution_mode == "replay"
    assert analysis.aggregate.successful == 1
    assert analysis.aggregate.failed == 149
    assert next(item for item in analysis.results if item.response_id == response_id).status == "successful"
