## Done

- Step 0: branded/unbranded aggregates and computed-summary guard (`27d132b`, `3570834`).
- Step 1: docs: `CLAUDE.md`, plain-language `SPEC.md`, `IMPLEMENTATION_PLAN.md`, `STATUS.md`; `AGENTS.md` is a pointer (`309ebcf`, `dcbf4fe`, `46a6684`).
- Step 2a: `classification.py` split into a package (`8cccaf2`).
- Step 2b: analyst-only import and analysis; required decision comment; checked over real HTTP (`8b9c338`, `f9e4c65`, `a226137`). Private knowledge base ignored (`a38acad`).
- Step 3a and 3b: limits measured (one approved probe); rule classifier, router, token pacing, quota stop, skip list, 39-answer sample, plan-only runner (`3780f11`, `872a28f`, `6c5483a`, `950ce0a`, `4e30239`).
- Step 4: baseline, report evidence checker, one-command comparison, regression tests. 94 tests pass; frozen hashes re-verified unchanged; no network used. Committed.

## In progress

- Step 3c: **you are running the live Groq send yourself.** I have not touched its database or output file. Paste the printed summary here when it finishes.

## Needs your call

- **Step 4b, a real findings generator, is approved.** Today's report text is generic pipeline wording and its evidence is the first three responses, not tied to any claim. It starts after your live run finishes (it needs the real results), and I will show you the design before writing code.
- Step 4 result worth knowing: on held-out, the keyword baseline ties the model at 4 of 8 exact passes, because the model failed validation on 3 cases. Both miss the one recommendation case. The model beats the baseline on the development cases (4/4 vs 1/4), but those were used for tuning.
- Side effect of Step 2a, still open: the freeze tools read the deleted `classification.py` (see `docs/PROJECT.md` section 8). Left as is until a new freeze is needed.
- Cleanup candidate: `tools/benchmark_model.py`. Not deleted, as you asked.
- Your real active hours, for the decision note (Step 5).
