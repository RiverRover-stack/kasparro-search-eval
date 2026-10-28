# ADR 0004: Groq strict-structured-output fallback

Status: accepted for integration, live evaluation pending credentials, 29 October 2026.

The local `gemma3:4b` adapter is not the production-quality classifier. Explicit `num_ctx=16384`
removed the maximum-input truncation mechanism, but repeated development-only checks still failed the
semantic/evidence gate on the shortest 3,855-character case. No held-out case was used for tuning.

Use Groq as the first hosted fallback behind the existing classifier interface. The default model is
the production model `openai/gpt-oss-20b`, with strict JSON Schema output, at most two 120-second
attempts, a 2,048-token completion cap, the same 20,000-character input limit, exact source-evidence
validation, and deterministic removal only of excerpts attached to inactive fields. Raw provider
output and provider diagnostics remain persisted.

The choice follows Groq's current official documentation: strict structured output is supported for
`openai/gpt-oss-20b`, and the production model has a 131,072-token context window. The integration uses
the OpenAI-compatible chat-completions HTTP API without adding an SDK dependency.

- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/models
- https://console.groq.com/docs/openai

`GROQ_API_KEY` is read only from the environment and is never stored in attempts, logs, exports, or
source files. Mocked tests verify request shape and strict schema handling. Model quality, latency,
coverage, and cost remain unknown until an approved live development run succeeds. Held-out evaluation
is allowed only after provider/model/prompt settings are frozen.
