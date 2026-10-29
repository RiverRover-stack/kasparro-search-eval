## Done

- Step 0: committed the branded/unbranded aggregates and the computed-summary guard (`27d132b`, `3570834`). Pack check, pytest and `git diff --check` all passed first.
- Step 1 (docs): wrote `CLAUDE.md`, `SPEC.md`, `IMPLEMENTATION_PLAN.md`, `STATUS.md`; `AGENTS.md` now points to `CLAUDE.md`. A reviewer agent fact-checked them against the code; I confirmed and fixed the discrepancies. Awaiting your review.

## In progress

- Nothing. Waiting for the owner to assess Step 1.

## Needs your call

- Approve commits for the Step 1 docs.
- The original `AGENTS.md` was untracked and is gone from disk, so it cannot be recovered. Its rules were folded into `CLAUDE.md` from the session text and `AGENTS.md` is now a pointer. Check nothing you relied on is missing.
- `POST /datasets` and `POST /analyses` have no analyst check, and the reviewer comment is optional (the assignment expects analyst-only import/analysis and a comment on every decision). Plan Step 2b fixes both as a behaviour change in its own commit; confirm.
- Active hours are not logged anywhere. Tell me your real hours so far for the decision note.
