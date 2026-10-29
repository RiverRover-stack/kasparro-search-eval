## Done

- Step 0: branded/unbranded aggregates and computed-summary guard (`27d132b`, `3570834`).
- Step 1: docs: `CLAUDE.md`, plain-language `SPEC.md`, `IMPLEMENTATION_PLAN.md`, `STATUS.md`; `AGENTS.md` is a pointer (`309ebcf`, `dcbf4fe`, `46a6684`).
- Step 2a: `classification.py` split into a package (`8cccaf2`).
- Step 2b: analyst-only import and analysis; required decision comment; checked over real HTTP (`8b9c338`, `f9e4c65`, `a226137`). Private knowledge base ignored (`a38acad`).
- Step 3a: measured limits and request sizes; one approved probe (no dataset content). Console limits for `gpt-oss-120b`: 30 requests/min, 1,000/day, 8,000 tokens/min, 200,000 tokens/day.
- Step 3b: rule classifier and router, token-paced Groq calls, daily-quota stop (run ends `interrupted`), skipped responses with reasons, deterministic sample, plan-only runner. 72 tests pass. Committed.
- Scope you chose: rules for the 78 answers without the brand name, Groq for a fixed sample of 39 mention answers (13 per engine), 33 skipped with reasons. Plan-only dry run: about 98K input tokens, at most about 178K if the daily cap charges the reserved output, about 25 minutes.

## In progress

- Nothing running. Nothing has been sent to Groq beyond the one probe.

## Needs your call

- **Step 3c, the live send.** 39 archived answers would go to Groq on your free plan. Cost about $0. It uses a fresh database (`--database-url sqlite:///backend/live-run.db`). I will show you the exact 39 response IDs and the command first; nothing is sent without your explicit go-ahead.
- Side effect of Step 2a, still open: the freeze tools read the deleted `classification.py` (see `docs/PROJECT.md` section 8). Left as is until a new freeze is needed.
- Cleanup candidate: `tools/benchmark_model.py`. Not deleted, as you asked.
- Your real active hours, for the decision note (Step 5).
