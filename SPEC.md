# Kasparro Visibility Backend: what it does

Last updated 29 October 2026. This describes behaviour that exists today, and marks anything that
does not exist yet. The work still to do is in [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).
Contributor rules are in [`CLAUDE.md`](CLAUDE.md).

## 1. The product in one paragraph

Kasparro helps brands see how they appear in AI answers. This backend studies Kasparro itself. It
takes a saved snapshot of 50 questions and the 150 answers that ChatGPT, Gemini and Google AI Mode
gave on 31 July 2026. For each answer it records whether Kasparro was absent, mentioned or
recommended, turns that into a simple score, and builds a report with three findings and three
suggested next steps. A person (the **analyst**) edits the report. A second person (the **reviewer**)
approves or rejects it. Only an approved version can be exported.

The question it answers: *where does Kasparro appear to be winning or losing in this snapshot, what
evidence supports that, and what should be investigated or changed next?*

It is a snapshot of one day, not a live ranking. Model output is a suggestion for a human to check,
not fact.

## 2. The flow

```
input files → check → classify each answer → score → draft report
                                                          ↓
                         analyst edits (each edit = new draft version)
                                                          ↓
                                  analyst submits (version is frozen)
                                                          ↓
                      reviewer approves or rejects that exact version
                                                          ↓
                                  approved version can be exported
```

## 3. The pieces

**Import.** Reads the prompts, responses, citations and provider payloads and checks them. Bad
records are rejected one by one with a reason; good ones are kept. The original records, their IDs
and a content hash are stored untouched. Importing the same run twice reuses the first import and
creates no duplicates. A *different* file under the same run ID is refused with a conflict error.

**Classify.** For each answer, a classifier fills in a fixed form (version `classification-v1`):
mentioned, recommended, negatively described, competitors named, position if one is stated, quoted
evidence, and how sure it is. The classifier can be:

| Mode | What it is | What it proves |
|---|---|---|
| `stub` | Fixed fake answers | Plumbing only |
| `replay` | Pre-supplied answers per response ID | Plumbing only |
| `local_ollama` | Local model (`gemma3:4b`) | Tried; did not pass our reliability checks |
| `hosted_groq` | Groq-hosted model, key from the environment | The real model path |

Every result and trace records which mode produced it. Answers are treated as untrusted text: they
cannot change permissions, identity or tools.

**Limits per answer.** At most 2 attempts, 120 seconds per attempt, 2,048 output tokens. An answer
longer than 20,000 characters is **skipped** with a reason; it is never silently cut short.

**Checks on model output.** The output must match the form. Every quoted excerpt must appear exactly
in the archived answer, or the attempt is rejected. If the model says Kasparro is mentioned but the
word is not in the text (or the reverse), that attempt is also rejected; the model's answer is never
silently replaced. After two rejected attempts the response is `failed`. A matching quote shows the
text is real, not that the model understood it.

**Score.** See section 4.

**Report.** One draft per finished analysis, built by plain code from the stored results: exactly
three diagnostics and three remedies, each linked to specific response results. The model is used
for classification only.

**Review.** See section 5.

## 4. How the score works

Each successfully classified answer gets one number:

| Situation | Score |
|---|---|
| Kasparro not mentioned | 0 |
| Mentioned, not recommended | 25 |
| Recommended | 100 |

Negative description, position in a list, competitors and whether links were returned are **kept as
separate fields**, not folded into the number. The score measures visibility and endorsement. It
does not measure whether the answer is accurate, or any business result.

**Every answer ends in exactly one state:** `successful`, `failed` or `skipped`. A failed or skipped
answer has **no score**. It is never counted as a zero, because failing to analyse an answer says
nothing about whether the brand appeared.

**Averages** weight each successful answer equally and always show the counts beside them:
eligible, successful, failed, skipped. A group with no successful answers has no score.

**Worked example.** One engine has 50 eligible answers: 40 successful, 6 failed, 4 skipped. Of the 40,
25 score 0, 10 score 25 and 5 score 100. Average = (0×25 + 25×10 + 100×5) / 40 = 18.75. The report
shows "18.75 from 40 of 50 answers; 6 failed, 4 skipped", never just "18.75".

**Comparing engines** uses only prompts that were successfully analysed for *every* engine, so each
engine is judged on the same questions.

**Grouping prompts.** Prompts 1–30 of the supplied run are labelled *branded* (the question names
Kasparro) and 31–50 *unbranded* (`prompt-categories-v1`). This describes the question, not the answer.
Any other run or prompt is shown as *unmapped*.

**Citations** are stored as they were returned, one row per occurrence. Analysis results currently
carry only a yes/no "citations present" flag. Unique-link counts are **not implemented**. If added,
the rule is to de-duplicate exact URL strings *within one response* only and to say so in the report.
A returned link does not mean the page supports the claim.

## 5. Report review rules

- A report version is **draft**, **submitted**, **approved** or **rejected**.
- Every edit creates a new draft version. Nothing is overwritten.
- Edits may change the findings and remedies, but **not** the computed scores and counts. Trying to
  returns `422` with code `computed_summary_immutable`.
- **Submitting** freezes that version. Reviewer decisions attach only to that exact version.
- Only the **reviewer** may approve or reject, and every decision needs a non-blank comment (a
  missing or blank one returns `422`, code `comment_required`, and the version stays submitted).
- Export works only for an approved version. The default is the latest version; if it is unapproved
  or rejected, export is refused. A caller may name an **older** approved version, which exports with
  its version clearly identified. It does not make a newer draft approved.
- Who a caller is comes from a secret token configured on the server, never from a name or role the
  caller types. The tokens are `KASPARRO_ANALYST_TOKEN` and `KASPARRO_REVIEWER_TOKEN`.
- Report events (created, edited, submitted, approved, rejected, exported) are recorded with actor,
  time and version, and never store a token. Dataset imports and analysis runs are not audited yet.

## 6. API

| Method and path | Who | Purpose |
|---|---|---|
| `GET /health` | anyone | Service and database check |
| `POST /datasets` | analyst | Import the input pack |
| `POST /analyses` | analyst | Run a classifier over a dataset |
| `GET /analyses/{id}` | anyone | Results, counts, engine and category averages |
| `POST /reports` | analyst | Create a draft report from an analysis |
| `GET /reports/{id}` | analyst or reviewer | Read a report and its versions |
| `PATCH /reports/{id}` | analyst | Edit; creates a new draft |
| `POST /reports/{id}/submit` | analyst | Freeze a version for review |
| `POST /reports/{id}/decision` | reviewer | Approve or reject a submitted version |
| `GET /reports/{id}/export?version_id=` | analyst or reviewer | Export an approved version |

Interactive docs are at `/docs` when the server runs. Send the token as `Authorization: Bearer <token>`.

**Errors** from the app's own checks return a safe message and a request ID, with the right status.
Two exceptions today: a malformed request body (FastAPI's default `422`) and unknown routes or wrong
methods (`404`/`405`) return the framework's default body without a `code` or request ID, though the
`X-Request-ID` header is still set. Statuses: `401` no token, `403`
unknown token or wrong role, `503` fewer than two tokens configured on the server, `404`
not found, `409` conflict (changed content under an existing run ID, analysis already running,
second report for one analysis, submitting a stale or non-draft version, deciding a non-submitted
version, exporting an unapproved version), `422` invalid input. Report errors carry a stable `code`
such as `version_not_approved` or `computed_summary_immutable`.

**Running.** One analysis at a time per process; a second request gets `409`. The request stays open
until the run finishes, so a full hosted run is a long call. A run left `running` when the server
restarts is marked `interrupted` at startup. Full resume is out of scope.

## 7. Evidence on model quality

- Local `gemma3:4b` failed the development checks and is not used for the full run.
- Hosted `openai/gpt-oss-120b` (prompt v6, frozen) passed 4 of 4 development cases. On the 8
  untouched held-out cases it produced valid output for 5 and matched all four expected labels on 4;
  it found none of the one positive recommendation case. Those artifacts are frozen and must not be
  rerun, edited or tuned against.
- The code's default Groq model is `openai/gpt-oss-20b`, which was **not** the model evaluated. Set
  `KASPARRO_GROQ_MODEL=openai/gpt-oss-120b` for any real run.
- No model has yet processed all 150 answers. Until it does, no report built from real model output
  exists.
- 12 supplied responses were labelled by hand before tuning (4 per engine; 4 for development, 8
  held out), plus 2 clearly marked synthetic edge cases. See `evaluation/labels-v1.json`.

## 8. What this system does not claim

- That scores show ranking, traffic or revenue effects.
- That a quoted excerpt means what the model says it means.
- That a returned citation supports the claim next to it.
- That any "possible explanation" in a report is a verified cause. They are hypotheses with a
  stated way to test them.
- That the snapshot reflects today's AI answers.
- That stub or replay runs say anything about model quality, speed or cost.

## 9. Which test covers which rule

| Rule | Test |
|---|---|
| Lossless, repeatable import | `tests/test_importer.py::test_full_pack_import_is_lossless_and_idempotent` |
| Bad records, missing parents | `tests/test_importer.py` (schema, duplicate, dependency, parent-mismatch tests) |
| Changed content under same run ID | `tests/test_importer.py::test_changed_content_under_existing_run_id_conflicts` |
| Output form and score values | `tests/test_classification.py` (contract tests, `test_visibility_score`) |
| Timeout, malformed output, oversize | `tests/test_classification.py` |
| Fabricated excerpt rejected | `tests/test_classification.py::test_fabricated_excerpt_is_rejected` |
| Failure is not absence; partial failure keeps good results | `tests/test_analysis.py::test_partial_failure_and_oversized_input_keep_valid_results` |
| Counts and shared-prompt comparison | `tests/test_analysis.py::test_stub_analysis_persists_terminal_results_and_aggregates` |
| Unmapped runs do not inherit categories | `tests/test_analysis.py::test_unknown_run_does_not_inherit_frozen_prompt_categories` |
| Draft, submit, decide, export, roles, older version | `tests/test_reports.py::test_report_lifecycle_authorization_immutability_and_versioned_export` (role check is called directly on the function, not over HTTP) |
| Summary cannot be edited | `tests/test_reports.py::test_report_rejects_changed_computed_summary` |
| Foreign evidence rejected | `tests/test_reports.py::test_report_rejects_foreign_evidence_reference` |
| Health and API docs | `tests/test_health.py` |
| Import and analysis are analyst-only; decision is reviewer-only | `tests/test_auth.py` (checks each route's dependencies and the role functions; not a live HTTP call) |
| Decision needs a comment | `tests/test_reports.py::test_decision_requires_a_reviewer_comment` |

Still without a dedicated test (listed in the plan): an unsupported diagnostic claim, and a named
regression for the documented model failure.
