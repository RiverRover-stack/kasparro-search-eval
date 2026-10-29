## Done

- Step 0: branded/unbranded aggregates and computed-summary guard.
- Step 1: docs: `CLAUDE.md`, plain-language `SPEC.md`, `IMPLEMENTATION_PLAN.md`, `STATUS.md`; `AGENTS.md` is a pointer.
- Step 2a/2b: `classification.py` split into a package; analyst-only import and analysis; required decision comment.
- Step 3a/3b: limits measured; rule classifier, router, token pacing, quota stop, skip list, 39-answer sample, plan-only runner.
- Step 3c: the owner ran the live send. Status `completed`; 150 accounted for: 105 successful, 12 failed, 33 skipped. Groq: 27 valid, 12 failed of 39 (11 schema rejections on the quote list, 1 contract error). Output in `evaluation/live-run-groq-sample.json` (not committed yet).
- Step 4: baseline, report evidence checker, one-command comparison, regression tests. 94 tests pass.
- Docs reorganised into three sets (reader `README.md`; private `docs/PROJECT.md` and `docs/AI_CONTEXT.md`; agent docs). Not committed yet.
- 2026-10-29: Step 4b findings generator built (`backend/app/findings.py`), report text now uses real counts. Rule changed (owner-approved) to one diagnostic per kind: unbranded, branded outlier engine, model findings. Tests, check_pack and the evidence checker on the live run pass. Not committed.
- 2026-10-29: Step 4b review fixes: new report summary no longer holds the blended average (Option A); wording follows the numbers; held-out sentence corrected; ADR 0006 now "proposed"; 120 tests. Not committed.
- 2026-10-29: Step 4b D1/D2 now carry verbatim excerpts in `evidence_needed`; evidence checker verifies every quoted excerpt against the archived answer; 127 tests. Not committed.
- 2026-10-29: Step 5 submission pack built, not committed. New: `.env.example` (+ test that it lists every variable in `config.py` and keeps secrets blank), README full-flow walk-through, `tools/export_analysis_output.py` (+ 6 tests) and `evaluation/analysis-output.json`, `docs/decision-note.md`, an empty active-time table in `journey/dev-notes.md`. 135 tests.
- 2026-10-29: README walk-through run for real against a local Uvicorn process, stub mode, temporary database, dummy tokens, no network. Status codes seen: import 200, analyse 200, create report 200, submit 200, export before approval 409, reject 200, edit 200, resubmit 200, analyst tries to decide 403, approve 200, export 200; no token 401. Versions ended as 1 rejected, 2 approved. Only difference from the README: the database path pointed to a temp folder instead of `backend/demo.db`.
- 2026-10-29: Reviewer finding on D2 fixed (owner kept the frozen mapping). Prompts 026-030 are labelled branded but their text does not contain "Kasparro". `build_findings` takes `prompt_named` (ids of prompts whose text contains the brand, read from the stored prompts in `reports.py`); D2 cites only answers to those prompts and its observed pattern says how many branded-labelled prompts do not name the brand. Engine numbers unchanged. 7 new tests; 142 tests pass, `check_pack` and `git diff --check` clean. Not committed. The saved live-run report and `evaluation/analysis-output.json` were not regenerated, so they still show the old D2.
- 2026-10-29: Review items (2) to (7) fixed, 150 tests pass, `check_pack`, `git diff --check` and `tools/run_evaluation.py` clean. (2) the quote cutter always keeps the brand name inside a quote that says it names Kasparro (`_bounded`); (3) `tools/check_report_evidence.py` flags an empty quoted excerpt, and `run_evaluation.py` seeds an `empty_quote` defect (now 5); (4) remedy 2 now says the linked answers show what the engines say instead, not why or which brands overall; (5) D3's title is "What the classifier found in the answers it read (execution mode: ...)"; (6) coverage lines say "successful" (the cells do not split rule and model results) and the model notes say "successful model results"; (7) six weak tests strengthened. Not committed.

## In progress

- Nothing running. Step 5 is waiting for your review. Active hours are still blank.

## Needs your call

- Approve commits: the live-run result file, and the docs updates (README, onboarding, journey notes, `CLAUDE.md`, `.gitignore`, `SPEC.md`, plan, status).
- 2026-10-29: Step 4b is built and waiting for your review. Commit approval needed.
- Live-run facts: model found 26 mentioned-only, 1 recommended, 11 negative among 27 valid mention answers. Only 1 recommendation may mean the model under-detects them (on the held-out check only 5 of 8 cases gave a valid answer and the model found 0 recommendations among them).
- Side effect of Step 2a, still open: the freeze tools read the deleted `classification.py` (see `docs/PROJECT.md` section 8). Left as is.
- Cleanup candidate: `tools/benchmark_model.py`. Not deleted, as you asked.
- Your real active hours: the table in `journey/dev-notes.md` and `active_time` in `evaluation/analysis-output.json` are blank on purpose. Please supply them (also noted in `docs/decision-note.md`).
- 2026-10-29: Step 5 needs your review and commit approval (new files: `.env.example`, `docs/decision-note.md`, `evaluation/analysis-output.json`, `tools/export_analysis_output.py`, two test files).
- 2026-10-29: `evaluation/analysis-output.json` regenerated from the saved live run (no network): D2 now cites the three Gemini "Kaspr" answers and says 5 of 30 branded-labelled prompts do not name Kasparro; `known_issues` lists only what remains (the 5 mislabelled prompts in the frozen mapping, the freeze tools). `live-run-groq-sample.json` is the raw live-run record and holds no report text, so it was not touched. Active hours: owner said not needed; left blank.
- Not run live: the README flow was only run in stub mode. The hosted-Groq path was not run in Step 5 (no network, no key used). The Windows PowerShell 5.1 version was not tried; the commands ran in PowerShell 7.
