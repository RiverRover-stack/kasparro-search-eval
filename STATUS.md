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

## In progress

- Nothing running. Step 5 is waiting for your review. Active hours are still blank.

## Needs your call

- Approve commits: the live-run result file, and the docs updates (README, onboarding, journey notes, `CLAUDE.md`, `.gitignore`, `SPEC.md`, plan, status).
- 2026-10-29: Step 4b is built and waiting for your review. Commit approval needed.
- 2026-10-29 (reviewer): Step 4b D2 evidence is misleading on the live run. Prompts 026-030 are labelled "branded" in `prompt-categories-v1` but their text does not contain "Kasparro" (0 of 15 answers name it, every engine), and 2 of the 3 Gemini answers cited in D2 come from those prompts. The real Gemini gap is 3 answers (prompts 014, 022, 025) where Gemini wrote about "Kaspr", a different product. Decide: keep the frozen mapping and make D2 cite only answers to prompts that name Kasparro (and say that 5 of 30 "branded" prompts per engine do not), or approve a mapping v2.
- Live-run facts: model found 26 mentioned-only, 1 recommended, 11 negative among 27 valid mention answers. Only 1 recommendation may mean the model under-detects them (on the held-out check only 5 of 8 cases gave a valid answer and the model found 0 recommendations among them).
- Side effect of Step 2a, still open: the freeze tools read the deleted `classification.py` (see `docs/PROJECT.md` section 8). Left as is.
- Cleanup candidate: `tools/benchmark_model.py`. Not deleted, as you asked.
- Your real active hours: the table in `journey/dev-notes.md` and `active_time` in `evaluation/analysis-output.json` are blank on purpose. Please supply them (also noted in `docs/decision-note.md`).
- 2026-10-29: Step 5 needs your review and commit approval (new files: `.env.example`, `docs/decision-note.md`, `evaluation/analysis-output.json`, `tools/export_analysis_output.py`, two test files).
- Open review items, recorded not fixed (also in `known_issues` of `evaluation/analysis-output.json`): (1) the D2 problem above; (2) the quote cutter can drop the brand name from a quote labelled as naming it (not hit on live data); (3) `tools/check_report_evidence.py` accepts an empty quote; (4) remedy 2 says the archive cannot show what engines say instead, while D1 quotes it; (5) D3's title is wrong for a plain stub run; (6) "valid" in the coverage lines covers rule-settled and model results; (7) several weak tests.
- Not run live: the README flow was only run in stub mode. The hosted-Groq path was not run in Step 5 (no network, no key used). The Windows PowerShell 5.1 version was not tried; the commands ran in PowerShell 7.
