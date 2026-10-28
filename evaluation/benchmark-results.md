# Context feasibility benchmarks

## 28 October 2026 — maximum supplied response

- Selection: longest archived answer, response `0f38b477-9f3c-44a8-9d10-0b6016db6150`.
- Input: 10,481 characters, passed in full with no truncation.
- Adapter: local Ollama `gemma3:4b`, prompt `visibility-classifier-v1`, two attempts,
  120-second per-attempt limit, 2,048 configured output-token limit.
- Attempt 1: 92,917 ms; incomplete JSON; rejected by strict validation.
- Attempt 2: 6,384 ms; incomplete JSON; rejected by strict validation.
- Validated result: no.

This shows that the maximum supplied input can be submitted within the configured context and time
boundary, but it does **not** show reliable completion or model quality. Both outputs ended after
roughly 150 characters and also began with a literal-mention judgment inconsistent with the archived
answer. The case belongs to the held-out split, so this observation is recorded only as the required
context-feasibility benchmark and was not used to tune the prompt.

## 29 October 2026 — local development-only diagnosis

The installed `gemma3:4b` advertises a 131,072-token model context. Ollama 0.32.5 was running with no
explicit project context setting; Ollama documents a 4K default below 24 GiB VRAM. The adapter now sets
`num_ctx=16384`. On the shortest development case (3,855 characters), the provider reported roughly
1,200–1,400 prompt tokens and normal `stop` completions. The prior truncation therefore no longer
reproduced.

The remaining failures were semantic and evidentiary:

- Initial 16K run: complete valid JSON in 60.454 seconds, but negative characterization disagreed with
  the frozen development label.
- Revised definitions: the four semantic fields matched, but free-form quotes changed punctuation,
  Unicode, or paragraph structure and failed exact-source validation.
- Exact evidence enum: quotes became exact archived spans, but the model attached recommendation
  evidence while returning `recommended=false`; a retry timed out at 120 seconds.
- Deterministic removal of evidence attached only to inactive fields: the first attempt had the correct
  semantic labels but left no Kasparro-linked active evidence; the retry regressed the negative label.

Conclusion: explicit context configuration solved the incomplete-JSON symptom, but local
`gemma3:4b` did not pass even the shortest development case after bounded tuning. It is rejected as
the reliable classifier for this submission. The eight held-out cases remain untouched.

## 29 October 2026 — hosted development-only diagnosis

Groq strict structured output was exercised with the configured `openai/gpt-oss-120b` model. Initial
HTTP 403 responses were transport-level failures caused by the Python request signature; explicit
JSON `Accept`, content type, and application user-agent headers fixed that path. A subsequent isolated
run of development response `ac5bdf24-6a6e-49a0-abf5-2755ff3b42bc` returned validated output and
matched all four frozen labels.

The next four-case run did not yet clear the development gate:

- Three cases returned validated results matching all four expected labels.
- The third case first encountered the provider's 8,000-token-per-minute limit and then received
  Groq error `json_validate_failed` because its generated quote did not satisfy the large evidence
  enum.
- No held-out case was run or inspected for tuning.

The adapter now uses prompt `visibility-classifier-v6`, narrows the exact evidence enum to
Kasparro-relevant source spans, and treats Groq's `json_validate_failed` response as retryable. These
changes pass the local automated suite, but the previously failing third case has not been sent again:
that network verification requires explicit approval to transmit the archived response to Groq.
After the v6 change, the saved development artifact completed all four cases with
`openai/gpt-oss-120b`: every output validated and all four primary fields agreed with their frozen
labels. The development gate is therefore **4/4 passed**. Its configuration is recorded in
`frozen-hosted-config-v1.json`, including hashes of the development artifact, classifier, label set,
and held-out runner. This is development evidence only and is not evidence of held-out or production
reliability.

## 29 October 2026 — frozen hosted held-out result

The immutable `groq-held-out-120b.json` and Markdown summary record eight frozen cases. Five cases
produced contract-valid results (62.5% validation coverage), and four passed every expected field
(50% exact-case pass rate). Among validated cases, brand mention agreement was 5/8 with precision and
recall both 1.0 where defined; negative-characterization agreement was 5/8 with precision and recall
both 1.0 where defined; observable-position agreement was 5/8. Recommendation agreement was 4/8,
precision was undefined because there were no predicted positives, and recall was 0.0 for the one
positive recommendation case.

Three cases did not validate. Two exhausted both attempts with Groq HTTP 400
`json_validate_failed` responses because generated quotes did not satisfy the exact-source enum. One
exhausted both attempts after returning negative characterization for `Kaspr` while the deterministic
contract correctly required a `Kasparro` mention. A fourth case validated but missed the positive
recommendation label. Exact-source validation establishes traceability only; it does not establish
semantic correctness.

Decision: this evidence does not support accepting Groq for the full 150-response run. This conclusion
does not invent a numerical threshold: three of eight cases had no usable classification, and the only
positive recommendation case was missed. The frozen prompt will not be tuned from held-out failures.
No full hosted run has been made.
