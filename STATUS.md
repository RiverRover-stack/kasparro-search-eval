## Done

- Step 0: committed the branded/unbranded aggregates and the computed-summary guard (`27d132b`, `3570834`).
- Step 1 (docs): committed `CLAUDE.md`, `SPEC.md`, `IMPLEMENTATION_PLAN.md`, `STATUS.md`; `AGENTS.md` points to `CLAUDE.md` (`309ebcf`, `dcbf4fe`, `46a6684`).
- Step 2a: split `backend/app/classification.py` into a package with no behaviour change (`8cccaf2`).
- Step 2b: `POST /datasets` and `POST /analyses` now require the analyst token; every review decision needs a non-blank comment (`422 comment_required`). 59 tests pass (7 new, no existing test edited). Checked over real HTTP against a temporary database: 401 no token, 403 reviewer or unknown token, 200 analyst; decision 403 for analyst, 422 for missing or blank comment, 200 with comment; export 409 before approval and 200 after. Not committed yet.

## In progress

- Nothing. Waiting for the owner to assess Step 2b.

## Needs your call

- Approve the Step 2b commits, plus one more small commit for the `.gitignore` line that hides the private `docs/PROJECT.md` knowledge base.
- **Side effect of Step 2a:** `tools/benchmark_held_out.py` (`verify_freeze`) and `tools/freeze_hosted_evaluation.py` read `backend/app/classification.py`, which no longer exists, so they would fail if run. The held-out runner must never be rerun anyway, and the frozen hash still matches that file at commits `46a6684`, `e64dd22` and `4ab19f0`, so the evidence is intact. No test covers these tools. Options: (a) leave it and document it (cheapest, my recommendation until a new freeze is needed); (b) change both tools to hash the whole `classification/` package, which breaks verification against the old frozen manifest.
- **Cleanup candidate:** `tools/benchmark_model.py` (50 lines) is referenced nowhere and is superseded by `tools/benchmark_development.py`, which supports both providers. Its results survive in `evaluation/benchmark-results.md`. Delete? I have not touched it. Files in `PACK_MANIFEST.json` (`Assignment.*`, `START_HERE.txt`) must stay or `check_pack.py` fails.
- Next sub-step: 2c (`scoring.py`) or 2d (module docstrings), or skip both and move to Step 3 (the Groq limits check).
- Active hours are not logged anywhere. Give me your real total when convenient (needed in Step 5).
