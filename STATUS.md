## Done

- Step 0: committed the branded/unbranded aggregates and the computed-summary guard (`27d132b`, `3570834`).
- Step 1 (docs): committed `CLAUDE.md`, `SPEC.md`, `IMPLEMENTATION_PLAN.md`, `STATUS.md`; `AGENTS.md` points to `CLAUDE.md` (`309ebcf`, `dcbf4fe`, `46a6684`).
- Step 2a: split `backend/app/classification.py` into a package (`contract`, `prompt`, `adapters`, `ollama`, `groq`) with no behaviour change. Checked: 52 tests pass with no test edits; every old non-import line is present in the package. Not committed yet.

## In progress

- Nothing. Waiting for the owner to assess Step 2a.

## Needs your call

- Approve the Step 2a commit.
- Then say which sub-step is next: 2b (analyst-only import/analysis, required reviewer comment; changes behaviour), 2c (`scoring.py`), or 2d (module docstrings).
- Active hours are not logged anywhere. Give me your real total when convenient (needed in Step 5).
