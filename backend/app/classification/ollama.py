from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .adapters import ClassificationOutcome, ModelAttempt
from .contract import ClassificationResult, normalize_inactive_evidence
from .prompt import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    candidate_excerpts,
    strict_classification_schema,
)


class OllamaClassifier:
    def __init__(
        self,
        model: str = "gemma3:4b",
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        timeout_seconds: int = 120,
        max_attempts: int = 2,
        max_output_tokens: int = 2048,
        max_input_chars: int = 20000,
        context_tokens: int = 16384,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.max_output_tokens = max_output_tokens
        self.max_input_chars = max_input_chars
        self.context_tokens = context_tokens
        self.model_identifier = f"{model};num_ctx={context_tokens}"
        self.prompt_version = PROMPT_VERSION
        self.execution_mode = "local_ollama"

    def classify(self, answer_text: str, response_id: str | None = None) -> ClassificationOutcome:
        if len(answer_text) > self.max_input_chars:
            raise ValueError(
                f"Input has {len(answer_text)} characters; limit is {self.max_input_chars}"
            )
        attempts: list[ModelAttempt] = []
        prompt = f"{SYSTEM_INSTRUCTION}\n\nARCHIVED ANSWER START\n{answer_text}\nARCHIVED ANSWER END"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": strict_classification_schema(candidate_excerpts(answer_text)),
            "options": {
                "num_predict": self.max_output_tokens,
                "num_ctx": self.context_tokens,
                "temperature": 0,
            },
        }
        for attempt_number in range(1, self.max_attempts + 1):
            started = time.monotonic()
            raw_output: str | None = None
            validation_error: str | None = None
            provider_metadata: dict[str, object] = {"context_tokens": self.context_tokens}
            try:
                request = urllib.request.Request(
                    self.endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    envelope = json.loads(response.read().decode("utf-8"))
                raw_output = str(envelope["response"])
                provider_metadata.update(
                    {
                        key: envelope[key]
                        for key in (
                            "done",
                            "done_reason",
                            "prompt_eval_count",
                            "eval_count",
                            "total_duration",
                        )
                        if key in envelope
                    }
                )
                result = ClassificationResult.model_validate_json(raw_output)
                result, dropped = normalize_inactive_evidence(result)
                provider_metadata["dropped_inactive_excerpts"] = dropped
                result.verify_excerpts(answer_text)
                attempts.append(
                    ModelAttempt(
                        attempt_number=attempt_number,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        raw_output=raw_output,
                        validation_error=None,
                        provider_metadata=provider_metadata,
                    )
                )
                return ClassificationOutcome(
                    result=result,
                    attempts=attempts,
                    model_identifier=self.model_identifier,
                )
            except (KeyError, ValueError, TimeoutError, urllib.error.URLError) as exc:
                validation_error = f"{type(exc).__name__}: {exc}"
                if raw_output is not None and attempt_number < self.max_attempts:
                    payload["prompt"] = (
                        prompt
                        + "\n\nPREVIOUS OUTPUT REJECTED BY DETERMINISTIC VALIDATION:\n"
                        + validation_error
                        + "\nReturn a corrected complete JSON object. Do not repeat that error."
                    )
            attempts.append(
                ModelAttempt(
                    attempt_number=attempt_number,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    raw_output=raw_output,
                    validation_error=validation_error,
                    provider_metadata=provider_metadata,
                )
            )
        return ClassificationOutcome(
            result=None,
            attempts=attempts,
            model_identifier=self.model_identifier,
        )
