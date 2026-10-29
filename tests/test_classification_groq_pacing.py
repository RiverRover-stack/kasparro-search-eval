from __future__ import annotations

import io
import json
import math
import urllib.error

import pytest

from backend.app.classification import GroqClassifier, ProviderQuotaExhausted
from tests.test_classification import FakeResponse, result


class OkResponse(FakeResponse):
    def read(self) -> bytes:
        return json.dumps(
            {
                "choices": [
                    {"message": {"content": result().model_dump_json()}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            }
        ).encode("utf-8")


def install(monkeypatch, handler):
    sleeps: list[float] = []
    clock = [1000.0]
    monkeypatch.setattr("backend.app.classification.urllib.request.urlopen", handler)
    monkeypatch.setattr("backend.app.classification.time.sleep", sleeps.append)
    monkeypatch.setattr("backend.app.classification.groq.time.monotonic", lambda: clock[0])
    return sleeps


def test_pacing_sleeps_cost_over_rate_before_second_request(monkeypatch) -> None:
    bodies: list[bytes] = []

    def urlopen(request, **_kwargs):
        bodies.append(request.data)
        return OkResponse("")

    sleeps = install(monkeypatch, urlopen)
    classifier = GroqClassifier(api_key="k", tokens_per_minute=8000, max_output_tokens=2048)
    classifier.classify("No brand here.")
    classifier.classify("No brand here.")

    cost = math.ceil(len(bodies[0]) / 3.4) + 2048
    expected = cost / (0.9 * 8000 / 60)
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(expected, rel=0.01, abs=0.05)


def test_no_pacing_by_default(monkeypatch) -> None:
    sleeps = install(monkeypatch, lambda request, **_kw: OkResponse(""))
    classifier = GroqClassifier(api_key="k")
    classifier.classify("No brand here.")
    classifier.classify("No brand here.")
    assert sleeps == []


def rate_limited(message: str, calls: list[int]):
    def urlopen(request, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            body = json.dumps(
                {"error": {"message": message, "type": "tokens", "code": "rate_limit_exceeded"}}
            ).encode("utf-8")
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests", hdrs=None, fp=io.BytesIO(body)
            )
        return OkResponse("")

    return urlopen


def test_daily_quota_429_raises_without_retry(monkeypatch) -> None:
    calls: list[int] = []
    sleeps = install(monkeypatch, rate_limited("Rate limit reached. Please try again in 3m10s.", calls))
    with pytest.raises(ProviderQuotaExhausted) as raised:
        GroqClassifier(api_key="secret-test-key").classify("No brand here.")
    assert len(calls) == 1
    assert sleeps == []
    assert "429" in str(raised.value) and "secret-test-key" not in str(raised.value)


def test_short_429_still_retries(monkeypatch) -> None:
    calls: list[int] = []
    sleeps = install(monkeypatch, rate_limited("Rate limit reached. Please try again in 8s.", calls))
    outcome = GroqClassifier(api_key="k").classify("No brand here.")
    assert outcome.result is not None
    assert len(calls) == 2
    assert sleeps == [8.25]
