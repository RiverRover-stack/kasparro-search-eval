from __future__ import annotations

import json

import pytest

from backend.app.classification import ClassificationResult, OllamaClassifier, visibility_score


def result(**overrides) -> ClassificationResult:
    values = {
        "contract_version": "classification-v1",
        "brand_mentioned": False,
        "recommended": False,
        "negative_characterization": False,
        "competitors": [],
        "observable_position": None,
        "supporting_excerpts": [],
        "uncertainty": "low",
        "uncertainty_reason": "The answer is explicit.",
    }
    values.update(overrides)
    return ClassificationResult.model_validate(values)


@pytest.mark.parametrize(
    ("classification", "expected"),
    [
        (result(), 0),
        (result(brand_mentioned=True), 25),
        (result(brand_mentioned=True, recommended=True), 100),
        (
            result(
                brand_mentioned=True,
                recommended=True,
                negative_characterization=True,
            ),
            100,
        ),
    ],
)
def test_visibility_score(classification: ClassificationResult, expected: int) -> None:
    assert visibility_score(classification) == expected


def test_fabricated_excerpt_is_rejected() -> None:
    classification = result(
        brand_mentioned=True,
        supporting_excerpts=[{"kind": "mention", "quote": "Kasparro is recommended."}],
    )

    with pytest.raises(ValueError, match="not found"):
        classification.verify_excerpts("The answer only mentions Kasparro.")


def test_recommendation_requires_mention() -> None:
    with pytest.raises(ValueError, match="requires a brand mention"):
        result(recommended=True)


def test_mention_must_agree_with_archived_text() -> None:
    classification = result(brand_mentioned=True)

    with pytest.raises(ValueError, match="literal Kasparro presence"):
        classification.verify_excerpts("This answer discusses only generic tracking tools.")


class FakeResponse:
    def __init__(self, output: str) -> None:
        self.output = output

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"response": self.output}).encode("utf-8")


@pytest.mark.parametrize(
    "raw_output",
    [
        "",
        "not json",
        json.dumps(
            {
                "contract_version": "classification-v1",
                "brand_mentioned": "not-a-boolean",
                "recommended": False,
                "negative_characterization": False,
                "competitors": [],
                "observable_position": None,
                "supporting_excerpts": [],
                "uncertainty": "low",
                "uncertainty_reason": "Invalid label type.",
            }
        ),
        json.dumps(
            {
                "contract_version": "classification-v1",
                "brand_mentioned": True,
                "recommended": False,
                "negative_characterization": False,
                "competitors": [],
                "observable_position": None,
                "supporting_excerpts": [
                    {"kind": "mention", "quote": "Kasparro fabricated quotation"}
                ],
                "uncertainty": "low",
                "uncertainty_reason": "Fabricated evidence.",
            }
        ),
    ],
)
def test_invalid_provider_outputs_exhaust_bounded_attempts(monkeypatch, raw_output: str) -> None:
    monkeypatch.setattr(
        "backend.app.classification.urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(raw_output),
    )
    outcome = OllamaClassifier(max_attempts=2).classify("Kasparro appears here.")

    assert outcome.result is None
    assert len(outcome.attempts) == 2
    assert all(attempt.validation_error for attempt in outcome.attempts)


def test_timeout_exhausts_bounded_attempts(monkeypatch) -> None:
    def timeout(*_args, **_kwargs):
        raise TimeoutError("controlled timeout")

    monkeypatch.setattr("backend.app.classification.urllib.request.urlopen", timeout)
    outcome = OllamaClassifier(max_attempts=2).classify("No brand in this answer.")

    assert outcome.result is None
    assert len(outcome.attempts) == 2
    assert all("TimeoutError" in (attempt.validation_error or "") for attempt in outcome.attempts)


def test_oversized_input_is_rejected_without_truncation() -> None:
    with pytest.raises(ValueError, match="limit is 10"):
        OllamaClassifier(max_input_chars=10).classify("x" * 11)

