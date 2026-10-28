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
