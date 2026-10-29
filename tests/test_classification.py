from __future__ import annotations

import json
import io
import urllib.error

import pytest

from backend.app.classification import (
    ClassificationResult,
    GroqClassifier,
    OllamaClassifier,
    candidate_excerpts,
    normalize_inactive_evidence,
    strict_classification_schema,
    visibility_score,
)


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


# regression for the 28 Oct 2026 gemma3 failure (journey/dev-notes.md)
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


# regression for the 28 Oct 2026 gemma3 failure (journey/dev-notes.md)
def test_mention_must_agree_with_archived_text() -> None:
    classification = result(brand_mentioned=True)

    with pytest.raises(ValueError, match="literal Kasparro presence"):
        classification.verify_excerpts("This answer discusses only generic tracking tools.")


def test_evidence_kind_must_agree_with_classification_field() -> None:
    classification = result(
        brand_mentioned=True,
        recommended=False,
        supporting_excerpts=[{"kind": "recommendation", "quote": "Kasparro"}],
    )

    with pytest.raises(ValueError, match="recommendation excerpt contradicts"):
        classification.verify_excerpts("Kasparro appears here.")


def test_active_negative_label_requires_negative_evidence() -> None:
    classification = result(
        brand_mentioned=True,
        negative_characterization=True,
        supporting_excerpts=[{"kind": "mention", "quote": "Kasparro"}],
    )

    with pytest.raises(ValueError, match="negative characterization requires"):
        classification.verify_excerpts("Kasparro appears here.")


def test_inactive_evidence_is_deterministically_removed() -> None:
    classification = result(
        brand_mentioned=True,
        negative_characterization=True,
        supporting_excerpts=[
            {"kind": "recommendation", "quote": "Kasparro is positioned as useful."},
            {"kind": "negative_characterization", "quote": "Kasparro lacks evidence."},
        ],
    )

    normalized, dropped = normalize_inactive_evidence(classification)

    assert dropped == 1
    assert [item.kind for item in normalized.supporting_excerpts] == [
        "negative_characterization"
    ]
    normalized.verify_excerpts("Kasparro is positioned as useful. Kasparro lacks evidence.")


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


def test_ollama_request_sets_context_and_records_provider_metadata(monkeypatch) -> None:
    captured = {}
    valid = result().model_dump_json()

    class MetadataResponse(FakeResponse):
        def read(self) -> bytes:
            return json.dumps(
                {
                    "response": valid,
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 700,
                    "eval_count": 40,
                }
            ).encode("utf-8")

    def fake_urlopen(request, **_kwargs):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return MetadataResponse(valid)

    monkeypatch.setattr("backend.app.classification.urllib.request.urlopen", fake_urlopen)
    outcome = OllamaClassifier(context_tokens=16_384).classify("No brand here.")

    assert captured["payload"]["options"]["num_ctx"] == 16_384
    assert outcome.result is not None
    assert outcome.attempts[0].provider_metadata == {
        "context_tokens": 16_384,
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 700,
        "eval_count": 40,
        "dropped_inactive_excerpts": 0,
    }


def test_groq_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        GroqClassifier(api_key="")


def test_groq_strict_schema_and_adapter_contract(monkeypatch) -> None:
    captured = {}
    classification = result(
        brand_mentioned=True,
        supporting_excerpts=[{"kind": "mention", "quote": "Kasparro"}],
    )

    class GroqResponse(FakeResponse):
        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {"content": classification.model_dump_json()},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 40},
                }
            ).encode("utf-8")

    def fake_urlopen(request, **_kwargs):
        captured["authorization"] = request.headers["Authorization"]
        captured["accept"] = request.headers["Accept"]
        captured["user_agent"] = request.headers["User-agent"]
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return GroqResponse("")

    monkeypatch.setattr("backend.app.classification.urllib.request.urlopen", fake_urlopen)
    outcome = GroqClassifier(api_key="secret-test-key").classify("Kasparro appears here.")

    response_format = captured["payload"]["response_format"]["json_schema"]
    assert captured["authorization"] == "Bearer secret-test-key"
    assert captured["accept"] == "application/json"
    assert captured["user_agent"] == "KasparroVisibilityBackend/0.1"
    assert response_format["strict"] is True
    assert response_format["schema"] == strict_classification_schema(
        candidate_excerpts("Kasparro appears here.")
    )
    assert captured["payload"]["seed"] == 17
    assert captured["payload"]["reasoning_effort"] == "low"
    assert outcome.result == classification
    assert outcome.attempts[0].provider_metadata["completion_tokens"] == 40


def test_strict_schema_requires_and_closes_every_object() -> None:
    schema = strict_classification_schema()

    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    excerpt = schema["properties"]["supporting_excerpts"]["items"]
    assert set(excerpt["required"]) == set(excerpt["properties"])
    assert excerpt["additionalProperties"] is False


def test_groq_403_records_safe_details_and_does_not_retry(monkeypatch) -> None:
    body = json.dumps(
        {
            "error": {
                "message": "The model is blocked at the project level.",
                "type": "permissions_error",
                "code": "model_permission_blocked_project",
            }
        }
    ).encode("utf-8")

    def forbidden(request, **_kwargs):
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(body),
        )

    monkeypatch.setattr("backend.app.classification.urllib.request.urlopen", forbidden)
    outcome = GroqClassifier(api_key="secret-test-key").classify("Kasparro appears here.")

    assert outcome.result is None
    assert len(outcome.attempts) == 1
    attempt = outcome.attempts[0]
    assert attempt.validation_error == (
        "Groq HTTP 403: The model is blocked at the project level."
    )
    assert attempt.provider_metadata == {
        "http_status": 403,
        "provider_error": {
            "type": "permissions_error",
            "code": "model_permission_blocked_project",
            "message": "The model is blocked at the project level.",
        },
    }
    assert "secret-test-key" not in json.dumps(attempt.__dict__)


def test_groq_429_waits_before_bounded_retry(monkeypatch) -> None:
    calls = 0
    waits = []
    successful = result().model_dump_json()

    class SuccessfulResponse(FakeResponse):
        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {"message": {"content": successful}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 20},
                }
            ).encode("utf-8")

    def rate_limited_then_success(request, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            body = json.dumps(
                {
                    "error": {
                        "message": "Rate limit reached. Please try again in 1.5s.",
                        "type": "tokens",
                        "code": "rate_limit_exceeded",
                    }
                }
            ).encode("utf-8")
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(body),
            )
        return SuccessfulResponse("")

    monkeypatch.setattr(
        "backend.app.classification.urllib.request.urlopen", rate_limited_then_success
    )
    monkeypatch.setattr(
        "backend.app.classification.time.sleep", lambda seconds: waits.append(seconds)
    )
    outcome = GroqClassifier(api_key="secret-test-key").classify("No brand here.")

    assert outcome.result is not None
    assert len(outcome.attempts) == 2
    assert waits == [1.75]
    assert outcome.attempts[0].provider_metadata["retry_after_seconds"] == 1.5


def test_groq_json_schema_rejection_is_retried(monkeypatch) -> None:
    calls = 0
    successful = result().model_dump_json()

    class SuccessfulResponse(FakeResponse):
        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {"message": {"content": successful}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 20},
                }
            ).encode("utf-8")

    def schema_rejected_then_success(request, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            body = json.dumps(
                {
                    "error": {
                        "message": "Generated JSON did not satisfy the supplied schema.",
                        "type": "invalid_request_error",
                        "code": "json_validate_failed",
                    }
                }
            ).encode("utf-8")
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(body),
            )
        return SuccessfulResponse("")

    monkeypatch.setattr(
        "backend.app.classification.urllib.request.urlopen", schema_rejected_then_success
    )
    outcome = GroqClassifier(api_key="secret-test-key").classify("No brand here.")

    assert outcome.result is not None
    assert len(outcome.attempts) == 2
    assert outcome.attempts[0].provider_metadata["provider_error"]["code"] == (
        "json_validate_failed"
    )


def test_candidate_excerpts_are_exact_bounded_source_spans() -> None:
    answer = (
        "Unrelated distant material.\n\n"
        "Heading\n\nKasparro is useful. It can be expensive.\n"
        + ("x" * 1001)
    )

    candidates = candidate_excerpts(answer)

    assert "Kasparro is useful." in candidates
    assert "It can be expensive." in candidates
    assert "Unrelated distant material." not in candidates
    assert all(candidate in answer for candidate in candidates)
    assert all(len(candidate) <= 1000 for candidate in candidates)
    quote_schema = strict_classification_schema(candidates)["properties"][
        "supporting_excerpts"
    ]["items"]["properties"]["quote"]
    assert quote_schema["enum"] == candidates

