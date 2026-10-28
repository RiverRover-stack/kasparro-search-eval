# ADR 0002: Local model behind a bounded adapter

Status: accepted, 28 October 2026.

Use the installed `gemma3:4b` through an Ollama adapter first. The adapter applies a versioned
instruction, a strict JSON schema, zero temperature, a 120-second request timeout, no more than two
attempts, a 2,048-token output cap, and an explicit 20,000-character input limit. It verifies that
quoted excerpts occur in the archived answer. Replay and controlled stub implementations will use
the same `ClassificationResult` boundary. A hosted adapter is optional and must not change the
contract or consume unapproved credentials.

