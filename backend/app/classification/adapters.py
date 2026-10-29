from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from .contract import CLASSIFICATION_CONTRACT_VERSION, ClassificationResult
from .prompt import PROMPT_VERSION


@dataclass(frozen=True)
class ModelAttempt:
    attempt_number: int
    duration_ms: int
    raw_output: str | None
    validation_error: str | None
    provider_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ClassificationOutcome:
    result: ClassificationResult | None
    attempts: list[ModelAttempt]
    model_identifier: str
    prompt_version: str = PROMPT_VERSION
    execution_mode: str = "local_ollama"


class Classifier(Protocol):
    model_identifier: str
    prompt_version: str
    execution_mode: str

    def classify(self, answer_text: str, response_id: str | None = None) -> ClassificationOutcome: ...


class ControlledStubClassifier:
    """Deterministic engineering adapter; its labels are not model-quality evidence."""

    model_identifier = "controlled-stub-v1"
    prompt_version = PROMPT_VERSION
    execution_mode = "stub"

    def __init__(self, failures: dict[str, str] | None = None) -> None:
        self.failures = failures or {}

    def classify(self, answer_text: str, response_id: str | None = None) -> ClassificationOutcome:
        failure = self.failures.get(response_id or "")
        if failure:
            attempt = ModelAttempt(1, 0, None, failure)
            return ClassificationOutcome(
                result=None,
                attempts=[attempt],
                model_identifier=self.model_identifier,
                execution_mode=self.execution_mode,
            )
        match = re.search("kasparro", answer_text, flags=re.IGNORECASE)
        excerpts = []
        if match:
            excerpts = [{"kind": "mention", "quote": answer_text[match.start() : match.end()]}]
        result = ClassificationResult.model_validate(
            {
                "contract_version": CLASSIFICATION_CONTRACT_VERSION,
                "brand_mentioned": match is not None,
                "recommended": False,
                "negative_characterization": False,
                "competitors": [],
                "observable_position": None,
                "supporting_excerpts": excerpts,
                "uncertainty": "low",
                "uncertainty_reason": "Deterministic controlled stub output.",
            }
        )
        result.verify_excerpts(answer_text)
        raw_output = result.model_dump_json()
        return ClassificationOutcome(
            result=result,
            attempts=[ModelAttempt(1, 0, raw_output, None)],
            model_identifier=self.model_identifier,
            execution_mode=self.execution_mode,
        )


class ReplayClassifier:
    model_identifier = "evaluation-replay-v1"
    prompt_version = PROMPT_VERSION
    execution_mode = "replay"

    def __init__(self, results_by_response_id: dict[str, ClassificationResult]) -> None:
        self.results_by_response_id = results_by_response_id

    def classify(self, answer_text: str, response_id: str | None = None) -> ClassificationOutcome:
        result = self.results_by_response_id.get(response_id or "")
        if result is None:
            return ClassificationOutcome(
                result=None,
                attempts=[ModelAttempt(1, 0, None, "No replay result for response")],
                model_identifier=self.model_identifier,
                execution_mode=self.execution_mode,
            )
        try:
            result.verify_excerpts(answer_text)
        except ValueError as exc:
            return ClassificationOutcome(
                result=None,
                attempts=[ModelAttempt(1, 0, result.model_dump_json(), f"ValueError: {exc}")],
                model_identifier=self.model_identifier,
                execution_mode=self.execution_mode,
            )
        return ClassificationOutcome(
            result=result,
            attempts=[ModelAttempt(1, 0, result.model_dump_json(), None)],
            model_identifier=self.model_identifier,
            execution_mode=self.execution_mode,
        )
