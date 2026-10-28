from __future__ import annotations

from collections import defaultdict
from threading import Lock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .classification import Classifier, visibility_score
from .models import (
    AnalysisRun,
    CitationRecord,
    Dataset,
    ModelAttemptRecord,
    ResponseClassificationRecord,
    ResponseRecord,
    utc_now,
)
from .schemas import (
    AnalysisAggregateView,
    AnalysisResultView,
    AnalysisView,
    SharedPromptComparisonView,
)


class AnalysisNotFoundError(LookupError):
    pass


class AnalysisBusyError(RuntimeError):
    pass


_ANALYSIS_LOCK = Lock()


def execute_analysis(
    session: Session,
    dataset_id: str,
    classifier: Classifier,
    max_input_chars: int,
) -> AnalysisView:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise AnalysisNotFoundError(f"Dataset {dataset_id} was not found")
    if not _ANALYSIS_LOCK.acquire(blocking=False):
        raise AnalysisBusyError("Another analysis is already running in this process")
    try:
        responses = list(
            session.scalars(
                select(ResponseRecord)
                .where(ResponseRecord.dataset_id == dataset_id)
                .order_by(ResponseRecord.id)
            )
        )
        citation_response_ids = set(
            session.scalars(
                select(CitationRecord.response_id).where(CitationRecord.dataset_id == dataset_id)
            )
        )
        run = AnalysisRun(
            id=str(uuid4()),
            dataset_id=dataset_id,
            status="running",
            execution_mode=classifier.execution_mode,
            model_identifier=classifier.model_identifier,
            prompt_version=classifier.prompt_version,
            eligible_count=len(responses),
        )
        session.add(run)
        session.commit()

        for response in responses:
            if len(response.answer_text) > max_input_chars:
                result_record = ResponseClassificationRecord(
                    analysis_run_id=run.id,
                    response_id=response.id,
                    prompt_id=response.prompt_id,
                    engine=response.engine,
                    status="skipped",
                    reason=(
                        f"oversized_input: {len(response.answer_text)} characters exceeds "
                        f"the {max_input_chars} character limit"
                    ),
                    classification=None,
                    visibility_score=None,
                    citation_present=response.id in citation_response_ids,
                )
                run.skipped_count += 1
                session.add(result_record)
                session.commit()
                continue

            try:
                outcome = classifier.classify(response.answer_text, response.id)
            except Exception as exc:  # adapter failures become explicit response failures
                outcome = None
                failure_reason = f"adapter_error: {type(exc).__name__}: {exc}"
                session.add(
                    ModelAttemptRecord(
                        analysis_run_id=run.id,
                        response_id=response.id,
                        attempt_number=1,
                        duration_ms=0,
                        execution_mode=classifier.execution_mode,
                        model_identifier=classifier.model_identifier,
                        prompt_version=classifier.prompt_version,
                        raw_output=None,
                        validation_error=failure_reason,
                        provider_metadata={},
                    )
                )
            else:
                failure_reason = None

            if outcome is not None:
                for attempt in outcome.attempts:
                    session.add(
                        ModelAttemptRecord(
                            analysis_run_id=run.id,
                            response_id=response.id,
                            attempt_number=attempt.attempt_number,
                            duration_ms=attempt.duration_ms,
                            execution_mode=outcome.execution_mode,
                            model_identifier=outcome.model_identifier,
                            prompt_version=outcome.prompt_version,
                            raw_output=attempt.raw_output,
                            validation_error=attempt.validation_error,
                            provider_metadata=attempt.provider_metadata,
                        )
                    )
                if outcome.result is None:
                    errors = [a.validation_error for a in outcome.attempts if a.validation_error]
                    failure_reason = errors[-1] if errors else "classifier_returned_no_result"

            if outcome is not None and outcome.result is not None:
                classification = outcome.result.model_dump(mode="json")
                status = "successful"
                score = visibility_score(outcome.result)
                run.successful_count += 1
            else:
                classification = None
                status = "failed"
                score = None
                run.failed_count += 1

            session.add(
                ResponseClassificationRecord(
                    analysis_run_id=run.id,
                    response_id=response.id,
                    prompt_id=response.prompt_id,
                    engine=response.engine,
                    status=status,
                    reason=failure_reason,
                    classification=classification,
                    visibility_score=score,
                    citation_present=response.id in citation_response_ids,
                )
            )
            session.commit()

        run.status = "completed"
        run.finished_at = utc_now()
        session.commit()
        return get_analysis(session, run.id)
    finally:
        _ANALYSIS_LOCK.release()


def _aggregate(records: list[ResponseClassificationRecord]) -> AnalysisAggregateView:
    successful = [record for record in records if record.status == "successful"]
    scores = [record.visibility_score for record in successful if record.visibility_score is not None]
    return AnalysisAggregateView(
        eligible=len(records),
        successful=len(successful),
        failed=sum(record.status == "failed" for record in records),
        skipped=sum(record.status == "skipped" for record in records),
        average_visibility_score=(sum(scores) / len(scores)) if scores else None,
    )


def _shared_prompt_comparison(
    records: list[ResponseClassificationRecord],
) -> SharedPromptComparisonView:
    all_engines = sorted({record.engine for record in records})
    successful_by_prompt: dict[str, dict[str, int]] = defaultdict(dict)
    for record in records:
        if record.status == "successful" and record.visibility_score is not None:
            successful_by_prompt[record.prompt_id][record.engine] = record.visibility_score
    shared = [scores for scores in successful_by_prompt.values() if set(scores) == set(all_engines)]
    averages: dict[str, float | None] = {}
    for engine in all_engines:
        values = [scores[engine] for scores in shared]
        averages[engine] = sum(values) / len(values) if values else None
    return SharedPromptComparisonView(
        shared_successful_prompts=len(shared),
        average_score_by_engine=averages,
    )


def get_analysis(session: Session, analysis_id: str) -> AnalysisView:
    run = session.get(AnalysisRun, analysis_id)
    if run is None:
        raise AnalysisNotFoundError(f"Analysis {analysis_id} was not found")
    records = list(
        session.scalars(
            select(ResponseClassificationRecord)
            .where(ResponseClassificationRecord.analysis_run_id == analysis_id)
            .order_by(ResponseClassificationRecord.response_id)
        )
    )
    by_engine: dict[str, AnalysisAggregateView] = {}
    for engine in sorted({record.engine for record in records}):
        by_engine[engine] = _aggregate([record for record in records if record.engine == engine])
    result_views = [
        AnalysisResultView(
            response_id=record.response_id,
            prompt_id=record.prompt_id,
            engine=record.engine,
            status=record.status,  # type: ignore[arg-type]
            reason=record.reason,
            classification=record.classification,
            visibility_score=record.visibility_score,
            citation_present=record.citation_present,
        )
        for record in records
    ]
    return AnalysisView(
        analysis_id=run.id,
        dataset_id=run.dataset_id,
        status=run.status,
        execution_mode=run.execution_mode,
        model_identifier=run.model_identifier,
        prompt_version=run.prompt_version,
        aggregate=_aggregate(records),
        by_engine=by_engine,
        shared_prompt_comparison=_shared_prompt_comparison(records),
        results=result_views,
    )
