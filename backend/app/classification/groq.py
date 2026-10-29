from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.request

from .adapters import ClassificationOutcome, ModelAttempt, ProviderQuotaExhausted
from .contract import ClassificationResult, normalize_inactive_evidence
from .prompt import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    candidate_excerpts,
    strict_classification_schema,
)


def build_payload(answer_text: str, model: str, max_output_tokens: int) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": f"ARCHIVED ANSWER START\n{answer_text}\nARCHIVED ANSWER END",
            },
        ],
        "temperature": 0,
        "seed": 17,
        "reasoning_effort": "low",
        "max_completion_tokens": max_output_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "kasparro_visibility_classification",
                "strict": True,
                "schema": strict_classification_schema(candidate_excerpts(answer_text)),
            },
        },
    }


class GroqClassifier:
    execution_mode = "hosted_groq"
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "openai/gpt-oss-20b",
        endpoint: str = "https://api.groq.com/openai/v1/chat/completions",
        timeout_seconds: int = 120,
        max_attempts: int = 2,
        max_output_tokens: int = 2048,
        max_input_chars: int = 20000,
        rate_limit_wait_cap_seconds: float = 60.0,
        tokens_per_minute: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is required for hosted_groq execution")
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.max_output_tokens = max_output_tokens
        self.max_input_chars = max_input_chars
        self.rate_limit_wait_cap_seconds = rate_limit_wait_cap_seconds
        self.model_identifier = model
        self.tokens_per_minute = tokens_per_minute
        self._next_allowed = 0.0

    def _pace(self, payload_bytes: int) -> None:
        if self.tokens_per_minute is None:
            return
        rate = 0.9 * self.tokens_per_minute / 60
        cost = math.ceil(payload_bytes / 3.4) + self.max_output_tokens
        now = time.monotonic()
        if now < self._next_allowed:
            time.sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + cost / rate

    def classify(self, answer_text: str, response_id: str | None = None) -> ClassificationOutcome:
        if len(answer_text) > self.max_input_chars:
            raise ValueError(
                f"Input has {len(answer_text)} characters; limit is {self.max_input_chars}"
            )
        payload = build_payload(answer_text, self.model, self.max_output_tokens)
        attempts: list[ModelAttempt] = []
        for attempt_number in range(1, self.max_attempts + 1):
            started = time.monotonic()
            raw_output: str | None = None
            validation_error: str | None = None
            provider_metadata: dict[str, object] = {}
            retryable = True
            try:
                body = json.dumps(payload).encode("utf-8")
                self._pace(len(body))
                request = urllib.request.Request(
                    self.endpoint,
                    data=body,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "KasparroVisibilityBackend/0.1",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    envelope = json.loads(response.read().decode("utf-8"))
                choice = envelope["choices"][0]
                raw_output = str(choice["message"]["content"])
                usage = envelope.get("usage", {})
                provider_metadata = {
                    "finish_reason": choice.get("finish_reason"),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                }
                result = ClassificationResult.model_validate_json(raw_output)
                result, dropped = normalize_inactive_evidence(result)
                provider_metadata["dropped_inactive_excerpts"] = dropped
                result.verify_excerpts(answer_text)
                attempts.append(
                    ModelAttempt(
                        attempt_number,
                        int((time.monotonic() - started) * 1000),
                        raw_output,
                        None,
                        provider_metadata,
                    )
                )
                return ClassificationOutcome(
                    result=result,
                    attempts=attempts,
                    model_identifier=self.model_identifier,
                    execution_mode=self.execution_mode,
                )
            except urllib.error.HTTPError as exc:
                provider_error: dict[str, object] = {}
                try:
                    error_body = json.loads(exc.read().decode("utf-8"))
                    if isinstance(error_body, dict) and isinstance(error_body.get("error"), dict):
                        details = error_body["error"]
                        provider_error = {
                            key: str(details[key])[:1000]
                            for key in ("type", "code", "message")
                            if details.get(key) is not None
                        }
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    provider_error = {}
                provider_metadata = {
                    "http_status": exc.code,
                    "provider_error": provider_error,
                }
                retry_after_seconds: float | None = None
                if exc.headers is not None:
                    retry_after = exc.headers.get("Retry-After")
                    if retry_after:
                        try:
                            retry_after_seconds = float(retry_after)
                        except ValueError:
                            retry_after_seconds = None
                summary = provider_error.get("message") or exc.reason or "request rejected"
                if retry_after_seconds is None:
                    match = re.search(
                        r"try again in (?:([0-9]+)m)?([0-9.]+)s", str(summary), re.IGNORECASE
                    )
                    if match:
                        retry_after_seconds = float(match.group(2)) + 60 * int(match.group(1) or 0)
                if retry_after_seconds is not None:
                    provider_metadata["retry_after_seconds"] = retry_after_seconds
                    if exc.code == 429 and retry_after_seconds > self.rate_limit_wait_cap_seconds:
                        raise ProviderQuotaExhausted(
                            f"Groq HTTP 429: {summary} (retry after {retry_after_seconds:g}s "
                            f"exceeds the {self.rate_limit_wait_cap_seconds:g}s wait cap)"
                        ) from None
                validation_error = f"Groq HTTP {exc.code}: {summary}"
                retryable = exc.code in {408, 409, 422, 429, 498, 500, 502, 503, 504}
                if provider_error.get("code") == "json_validate_failed":
                    retryable = True
            except (KeyError, IndexError, ValueError, TimeoutError, urllib.error.URLError) as exc:
                validation_error = f"{type(exc).__name__}: {exc}"
            attempts.append(
                ModelAttempt(
                    attempt_number,
                    int((time.monotonic() - started) * 1000),
                    raw_output,
                    validation_error,
                    provider_metadata,
                )
            )
            if not retryable:
                break
            if (
                attempt_number < self.max_attempts
                and provider_metadata.get("retry_after_seconds") is not None
            ):
                wait_seconds = min(
                    float(provider_metadata["retry_after_seconds"]) + 0.25,
                    self.rate_limit_wait_cap_seconds,
                )
                time.sleep(wait_seconds)
        return ClassificationOutcome(
            result=None,
            attempts=attempts,
            model_identifier=self.model_identifier,
            execution_mode=self.execution_mode,
        )
