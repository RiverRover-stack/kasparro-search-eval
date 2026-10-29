# CLAUDE.md

Guide for people and coding agents working in this repository. Read this first; it links to the
detail elsewhere instead of repeating it.

## What this project is

A small FastAPI + SQLite backend for the Kasparro AI-engineer assignment (`Assignment.pdf`). It reads
50 prompts and 150 archived AI answers (ChatGPT, Gemini, Google AI Mode), asks a model whether
Kasparro is absent, mentioned or recommended in each answer, scores that with fixed arithmetic,
builds a report with three diagnostics and three remedies, and lets a human analyst and reviewer
control which report version can be exported.

The model output is **input for human review, not fact.**

Flow: `source pack → validate → classify → score → report → analyst edit → submit → reviewer decision → approved export`

## Commands (Windows PowerShell, from the repo root)

```powershell
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
py -3 -m pip install -e ".[dev]"            # setup
py -3 tools\check_pack.py                   # input pack integrity (run first)
py -3 -m pytest -q                          # all tests (no network, no model needed)
py -3 -m pytest tests\test_reports.py -q    # one file while iterating
py -3 tools\run_evaluation.py               # baseline vs frozen model comparison -> evaluation/comparison-report.md (no network)
py -3 tools\run_live_analysis.py            # PLAN ONLY; sending needs --confirm-send, ask the owner first
git diff --check                            # whitespace check
py -3 -m uvicorn backend.app.main:app --reload   # run API; docs at http://127.0.0.1:8000/docs
```

Setup details and request examples: `docs/onboarding.md` (README is being rewritten in the plan).

## Documentation sets (keep them separate)

| Set | Files | Audience and style |
|---|---|---|
| Reader-facing | `README.md` | People viewing the project. Very simple words, short sentences, honest status. Never claim unbuilt work. |
| Owner's private reference | `docs/PROJECT.md`, `docs/AI_CONTEXT.md` (both gitignored) | The owner, and a paste-in brief for other AIs. Never track them. |
| Agent and contributor | `CLAUDE.md`, `SPEC.md`, `docs/adr/` | Precise, technical. |

After each milestone: update `STATUS.md` always (gitignored, local progress log); `README.md` if status or results changed;
`docs/PROJECT.md` and `docs/AI_CONTEXT.md` if the project's state changed.

## Where things live

| Path | Purpose |
|---|---|
| `backend/app/main.py` | FastAPI routes, error handlers, request IDs |
| `backend/app/auth.py` | Analyst/reviewer roles from bearer tokens in the environment |
| `backend/app/config.py` | `Settings` and `.env` loading (all environment variables) |
| `backend/app/importer.py` | Validate and store the input pack; idempotent re-import |
| `backend/app/classification.py` | Output contract, prompt, scoring function, stub/replay/Ollama/Groq classifiers (large; the plan splits it) |
| `backend/app/analysis.py` | Runs a classifier over every response; aggregates and engine comparison |
| `backend/app/reports.py` | Report drafts, versions, submit, decision, export, audit events |
| `backend/app/models.py`, `schemas.py`, `database.py` | SQLAlchemy tables, Pydantic API types, engine/session |
| `tests/` | pytest; service-level tests with in-memory SQLite (`conftest.py`) |
| `tools/` | `check_pack.py` plus benchmark and freeze scripts |
| `evaluation/` | Labelled cases and frozen results (see invariants) |
| `SPEC.md` | What it does |
| `IMPLEMENTATION_PLAN.md` (gitignored, local only) | What is left; not part of the repository |
| `STATUS.md` (gitignored, local only) | Current progress log; not part of the repository |
| `docs/adr/` | Decisions |
| `journey/` (gitignored, local only) | Measured development history; not part of the repository |

## Product invariants (do not break)

1. Do not modify `data/`, `provenance/`, `PACK_MANIFEST.json` or final evaluation artifacts without
   explicit approval for a new version.
2. Keep source IDs, raw records, provenance, citation occurrences and content hashes.
3. A failure is not brand absence. Every eligible response ends `successful`, `failed` or `skipped`.
4. Evidence excerpts must appear verbatim in the archived answer. That proves traceability, not meaning.
5. Scoring is deterministic: absent `0`, mentioned `25`, recommended `100`. Other fields stay
   separate; every aggregate shows its denominators.
6. A report has exactly three evidence-linked diagnostics and three remedies. Explanations are
   hypotheses until verified.
7. Submitting freezes a version; a decision binds only to that version; editing creates a new draft;
   only approved versions export.
8. Never rerun, overwrite or tune against an existing final held-out artifact.
9. Never expose credentials in code, commits, tests, logs, traces, audits, errors, screenshots or exports.

## Code conventions

- Match the surrounding style and comment density. Change only what the task needs.
- Business rules (scoring, authorization, lifecycle, export gates) live in plain, testable functions,
  not in route handlers. Routes stay thin.
- Validate every boundary with Pydantic: requests, model output, imported records.
- Bound every network call: timeout, retry limit, input and output size.
- Errors are structured: stable code, safe message, HTTP status, request ID. (Not yet true for
  malformed bodies and unknown routes; see `SPEC.md` section 6.)
- Make repeatable operations idempotent, and keep valid partial work when one record fails.
- Never silently switch model provider.
- Record state changes in credential-free audit events.
- Weigh privacy, cost, accessibility, interruption and recovery as requirements. Update tests, OpenAPI
  examples, docs and ADRs when behaviour or architecture changes.
- Schema changes need an additive, forward-safe migration. Keep API behaviour backward compatible
  unless a breaking change is approved.
- Add or update tests with every behaviour change. Never weaken a validation, permission or test to
  get a check green.
- Prefer small functions and explicit states over clever code. No abstractions for single use.

## Working with a human in the loop

- Inspect `git status` first and preserve existing changes. State the planned change and how it will
  be verified before editing.
- Work on **one plan step at a time**, then stop and let the owner assess. Do not start the next step.
- Say clearly which claims come from code, automated checks, live-provider runs, or are unknown.
- Stop and ask when evidence changes scope, or when a data, security or product-contract decision is needed.
- **Ask first** for: sending data to an external service, anything with cost, long live runs,
  changing frozen evidence, deleting things, commits, history edits, pushes, PRs, merges, releases.
- Check provider rate and token limits before any batch of hosted-model calls, and pace to fit them.

## Git

- Commit only after explicit approval. One coherent change per commit, with its tests.
- Messages: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, concise. No AI-attribution footer.
- Review `git diff --cached` before committing. Never amend, rebase, force-push, push, tag or open a
  PR without specific approval.
- Never commit `.env`, tokens, API keys or `*.db` files.

## Verification before calling something done

Run focused tests first, then all three gates: `check_pack.py`, `pytest -q`, `git diff --check`.
A change is done when its acceptance criteria and regression tests pass, docs match behaviour, and no
secrets, unrelated edits or unsupported claims remain. Say what was verified and what is still unknown.
Do not claim production readiness from stubs, mocks or one good run.

## Model and evaluation rules

- Execution modes are labelled everywhere: `stub`, `replay`, `local_ollama`, `hosted_groq`. Stub and
  replay prove mechanics, never model quality.
- Iterate only on the declared development cases in `evaluation/labels-v1.json`. Freeze the
  configuration before final evaluation, run the guarded held-out tool once, and keep failures.
- Do not invent a pass threshold after seeing results.

## Known gotchas

- Starlette's in-process `TestClient` hangs on this Windows / Python 3.13 setup. Tests call services
  directly and check the OpenAPI route list separately; verify HTTP with a real Uvicorn process.
- `.env` in the repo root is loaded by `config.py`; real environment variables override it. Tests must
  point at temporary env files so a developer's real key never leaks in.
- Python on Windows turns `\n` into `\r\n` when piping text to stdout. Write bytes if you pipe a patch.
- The code defaults `KASPARRO_GROQ_MODEL` to `openai/gpt-oss-20b`; the evaluated model is
  `openai/gpt-oss-120b`. Set it explicitly.
- Groq needs explicit `Accept`, content-type and user-agent headers, or it returns 403.
