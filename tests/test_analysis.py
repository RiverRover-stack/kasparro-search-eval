from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.analysis import _prompt_branding_groups, execute_analysis, get_analysis
from backend.app.classification import ClassificationOutcome, ControlledStubClassifier, ModelAttempt
from backend.app.importer import import_pack
from backend.app.models import ModelAttemptRecord, ResponseClassificationRecord
from backend.app.main import create_analysis, read_analysis
from backend.app.schemas import AnalysisCreateRequest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_unknown_run_does_not_inherit_frozen_prompt_categories() -> None:
    record = ResponseClassificationRecord(
        prompt_id="kasparro:ai_shortlisting:001", status="failed", visibility_score=None
    )
    _, groups = _prompt_branding_groups([record], "another-run")
    assert groups["unmapped"].failed == 1
    assert groups["unmapped"].average_visibility_score is None
    assert groups["branded"].eligible == 0


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
        assert fetched.prompt_mapping_version == "prompt-categories-v1"
        assert fetched.by_prompt_branding["branded"].eligible == 90
        assert fetched.by_prompt_branding["unbranded"].eligible == 60
        assert fetched.by_prompt_branding["unmapped"].eligible == 0
        assert fetched.by_prompt_branding["unmapped"].average_visibility_score is None
        assert fetched.shared_prompt_comparison.shared_successful_prompts == 50
        assert session.scalar(select(func.count()).select_from(ModelAttemptRecord)) == 150
        assert all(
            metadata == {}
            for metadata in session.scalars(select(ModelAttemptRecord.provider_metadata))
        )
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
    assert sum(group.failed for group in analysis.by_prompt_branding.values()) == 1
    assert sum(group.skipped for group in analysis.by_prompt_branding.values()) == analysis.aggregate.skipped


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


def test_hosted_endpoint_requires_configured_key(
    session_factory: sessionmaker[Session], monkeypatch
) -> None:
    monkeypatch.setattr(
        "backend.app.config.ENV_FILE", ROOT / "missing-test-environment-file"
    )
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        with pytest.raises(HTTPException) as caught:
            create_analysis(
                AnalysisCreateRequest(
                    dataset_id=dataset.dataset_id,
                    execution_mode="hosted_groq",
                ),
                session,
            )

    assert caught.value.status_code == 422
    assert "GROQ_API_KEY" in str(caught.value.detail)


def test_hosted_endpoint_uses_hosted_mode_and_persists_provider_metadata(
    session_factory: sessionmaker[Session], monkeypatch
) -> None:
    class HostedTestClassifier(ControlledStubClassifier):
        execution_mode = "hosted_groq"
        model_identifier = "hosted-test-model"
        prompt_version = "visibility-classifier-v6"

        def classify(self, answer_text: str, response_id: str | None = None):
            outcome = super().classify(answer_text, response_id)
            attempt = outcome.attempts[0]
            return ClassificationOutcome(
                result=outcome.result,
                attempts=[
                    ModelAttempt(
                        attempt.attempt_number,
                        attempt.duration_ms,
                        attempt.raw_output,
                        attempt.validation_error,
                        {"finish_reason": "stop", "prompt_tokens": 1},
                    )
                ],
                model_identifier=self.model_identifier,
                prompt_version=self.prompt_version,
                execution_mode=self.execution_mode,
            )

    class TestSettings:
        max_input_chars = 20_000
        groq_api_key = "configured-test-credential"
        groq_model = "hosted-test-model"

    monkeypatch.setattr("backend.app.main.Settings.from_environment", lambda: TestSettings())
    monkeypatch.setattr(
        "backend.app.main.GroqClassifier", lambda **_kwargs: HostedTestClassifier()
    )
    with session_factory() as session:
        dataset = import_pack(session, ROOT)
        analysis = create_analysis(
            AnalysisCreateRequest(
                dataset_id=dataset.dataset_id,
                execution_mode="hosted_groq",
            ),
            session,
        )
        metadata = list(session.scalars(select(ModelAttemptRecord.provider_metadata)))

    assert analysis.execution_mode == "hosted_groq"
    assert analysis.model_identifier == "hosted-test-model"
    assert analysis.prompt_version == "visibility-classifier-v6"
    assert analysis.aggregate.eligible == 150
    assert analysis.aggregate.successful == 150
    assert all(item == {"finish_reason": "stop", "prompt_tokens": 1} for item in metadata)
