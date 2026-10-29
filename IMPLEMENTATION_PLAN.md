# Implementation plan

Last updated 29 October 2026. What the system does today: [`SPEC.md`](SPEC.md). Rules for working
here: [`CLAUDE.md`](CLAUDE.md). Live progress: [`STATUS.md`](STATUS.md). How we got here:
[`journey/`](journey/).

**Goal:** a correct, complete, runnable flow that meets `Assignment.pdf`, with code a new contributor
can follow. The assignment caps active work at six hours. Optional extras (dashboard, Docker,
deployment) are out of scope.

**Working rule:** one step at a time. After each step, stop, summarise, propose small commits, and
wait for the owner. Nothing is committed, run against a paid or external service, or started on the
next step without approval.

## Where we stand

| Assignment requirement | State |
|---|---|
| Import, validate, no duplicates | Done, tested |
| Classify all 150 responses (success / failed / skipped) | Mechanics done; **real run not done** |
| Transparent 0/25/100 score, denominators, engine and category views | Done |
| Report with 3 diagnostics + 3 remedies; edit, submit, decide, export | Done, tested |
| Analyst-only import and analysis | **Gap:** `POST /datasets` and `/analyses` need no token |
| Reviewer comment on every decision | **Gap:** comment is optional |
| Health endpoint, API docs | Done |
| Required backend tests (invalid input, duplicates, timeout/malformed, wrong role, rejection blocks export, edit after approval) | Done at service level; wrong role is not yet tested through an HTTP endpoint (Step 2b adds that) |
| Malformed bodies and unknown routes return the structured error | **Gap:** framework default body, no `code` |
| Unique-link counting with the stated de-duplication rule | **Not implemented** (only a citations-present flag) |
| 8+ hand-labelled cases + 2 edge cases, split dev/held-out | Done (`evaluation/labels-v1.json`) |
| Rule-based baseline vs model, same cases | **Missing** |
| One command to rerun evaluation and write a comparison | **Missing** (logic is spread over four scripts) |
| Check that diagnostics have real evidence, incl. an unsupported-claim case | **Missing** |
| Failure → diagnosis → fix → regression test | Story exists; needs a named test and a write-up |
| `.env.example` | **Missing** |
| README with setup and request examples | **Missing** (stub only) |
| Analysis output JSON, one-page decision note | **Missing** |
| Active time, omissions, unfinished work | **Missing** |
| Model quality | Local model failed; Groq 120b passed 4/4 dev, valid on 5/8 held-out, exact on 4/8 |

## Steps

### Step 0: Secure existing work. Done
Committed the branded/unbranded aggregates and the computed-summary guard (`27d132b`, `3570834`).

### Step 1: Documentation. Done, awaiting review
`CLAUDE.md`, `SPEC.md`, this plan, `STATUS.md`; `AGENTS.md` points to `CLAUDE.md`.
Done when: the owner can follow the flow and the gaps from these files alone.

### Step 2: Make the code easy to change
Behaviour must not change; all tests stay green after each move.
- [ ] **2a. Split `classification.py`** (603 lines) into a package: `contract.py` (output form,
  versions), `prompt.py`, `adapters.py` (protocol, stub, replay), `ollama.py`, `groq.py`. Keep
  `from backend.app.classification import ...` working.
- [ ] **2b. Close the two access gaps:** require the analyst token on `POST /datasets` and
  `POST /analyses`; make the reviewer comment required. Add tests for each (wrong role denied;
  missing comment rejected). This one *does* change behaviour, so it is its own commit.
- [ ] **2c. Move scoring and aggregation** into `backend/app/scoring.py` (`visibility_score`, the
  aggregate and comparison helpers now inside `analysis.py`).
- [ ] **2d.** One-line docstring at the top of each `backend/app/` module.

Done when: pytest passes with the same tests, and the import surface is unchanged.
Trim first if time is short: 2d, then 2c.

### Step 3: The full Groq run (needs approval at 3a and again before 3b)
Sends all 150 archived answers to a hosted service, so it needs explicit approval and a limits check.
- [ ] **3a. Check limits, send nothing in bulk.** Read Groq's published limits for
  `openai/gpt-oss-120b` (requests and tokens per minute and per day, context size, max output).
  With approval, one minimal probe request to read the `x-ratelimit-*` headers for this account's
  real values. Estimate tokens for all 150 inputs locally. Then propose: delay between requests,
  output cap, any answer to skip, expected duration, and whether to split across days. Stop.
- [ ] **3b. Run it** with the agreed pacing and the frozen config
  (`evaluation/frozen-hosted-config-v1.json`). Not a held-out rerun. Cost must stay under US$5.
  Set `KASPARRO_GROQ_MODEL=openai/gpt-oss-120b` first: the code defaults to the unevaluated `20b`.
- [ ] **3c.** Save results to `evaluation/full-run-groq-120b.json` (counts, runtime, tokens, failures).
  If denied or it fails badly, fall back to replay mode and mark model quality unverified.

Note: earlier docs estimated 75–90 minutes at a 30-second gap, based on an 8,000 tokens-per-minute
limit seen in development. Re-measure in 3a; do not reuse that number.

### Step 4: Evaluation you can rerun
- [ ] **4a.** Rule baseline classifier (brand text present; recommendation and negative words near it).
- [ ] **4b.** `tools/run_evaluation.py`: one command that scores baseline and model on the same labelled
  cases (per-label precision and recall, coverage, failures), checks the score arithmetic separately,
  checks that every report excerpt is in its response, and writes `evaluation/comparison-report.md`.
  Reuse the metric code in `tools/benchmark_held_out.py`. Reads frozen model results; never reruns them.
- [ ] **4c.** Tests: unsupported diagnostic claim is flagged; a named regression test for the
  documented failure (reformatted quote rejected; a "mentioned" claim that disagrees with the literal
  text rejected, not overridden).

Done when: one command regenerates the report and the new tests pass.

### Step 5: Submission pack
- [ ] `.env.example` with every variable in `config.py` and blank secrets.
- [ ] `README.md`: setup, database start, test and evaluation commands, and PowerShell requests for
  analyse → edit → submit → reject → edit → submit → approve → export, plus a wrong-role denial.
- [ ] `evaluation/analysis-output.json`: scores and coverage, the 3 diagnostics, the 3 remedies, active time.
- [ ] `docs/decision-note.md` (about one page): scoring and aggregation, review design, alternatives,
  top remedy, the failure and fix, biggest risk, omissions, questions before release, AI assistance.
- [ ] Active-time log in `journey/dev-notes.md`. The owner supplies real hours; nothing is guessed.

## Deliberately out of scope

Dashboard, Docker, deployment, crawling, vector search, multiple agents, restart/resume of analyses,
simultaneous-review protection, approval expiry (described as future work in the decision note).

## Rules that never get cut

Tests, the one-command evaluation, honest reporting of failures, and credential safety.
