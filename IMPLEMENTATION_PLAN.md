# Kasparro Visibility Backend: Specification and Implementation Plan

Status: Implementation in progress; Phases 0, 1, and 3 completed. Phase 2 engineering is complete,
but no provider passed the reliability evidence needed for the full 150-response run.
Saved: 28 October 2026. All schedule times below are IST.
The schedule records the agreed targets; elapsed windows do not imply completed work.

Current verified progress:

- The original pack integrity checker passes for 50 prompts, 150 responses, and 2,439 citation
  occurrences.
- FastAPI, SQLite/SQLAlchemy persistence, `/health`, `POST /datasets`, request IDs, raw-record
  preservation, relationship validation, partial rejection, and idempotent import are implemented.
- Classification contract version 1, exact-excerpt verification, deterministic literal-mention
  checking, bounded Ollama execution, and the 0/25/100 score function are implemented.
- Fifty automated tests pass. A live Uvicorn check returned HTTP 200, documented both implemented
  paths, imported the complete pack with no rejections, and safely reused the repeated import.
- A median-length `gemma3:4b` sample initially failed traceability and mention checks. After the
  deterministic guard/prompt fix, the same sample validated on attempt 2. A full local-model run,
  reports, review, export, and the remaining documentation are not complete.
- Twelve supplied evaluation responses are now frozen in a versioned 4-development/8-held-out
  split, balanced across engines, with exact evidence and two synthetic edge cases. Prompt categories
  are frozen separately and held-out cases are prohibited from tuning.
- Provider provenance is linked to all 150 imported responses. Stub and replay analyses persist runs,
  attempts, terminal response outcomes, denominated aggregates, and shared-prompt comparisons through
  `POST /analyses` and `GET /analyses/{id}`.
- The 10,481-character maximum response was sent without truncation. Both bounded local-model attempts
  returned incomplete JSON (92.917 seconds and 6.384 seconds), so no validated classification or
  model-quality result is claimed. The held-out case was not used for tuning.

## 1. Outcome and architecture

Deliver a local, reproducible backend by **29 October 2026, 1:00 p.m. IST**, with final readiness by **7:00 p.m. IST**. Record the user's revised deadline separately from the original assignment instructions.

Use Python, FastAPI, Pydantic, SQLite, SQLAlchemy, and pytest. Expose REST endpoints with generated OpenAPI documentation. Keep application code in a dedicated `backend/` directory and preserve the supplied inputs unchanged.

The processing flow is:

**Import → validated records → local semantic classification → deterministic scoring → evidence-linked report → analyst edit → immutable submission → reviewer decision → approved export**

Use Ollama with the already installed `gemma3:4b` as the initial model. Benchmark it early; do not claim quality or completion until actual runs support those claims. Provide replay and controlled stubs for reproducibility and engineering tests.

Exclude dashboards, deployment, crawling, vector search, multi-agent orchestration, and automatic execution of remedies from the required build.

## 2. Contracts and behavior

### Data and persistence

Persist datasets, prompts, responses, citation occurrences, analysis runs, response results, reports, report versions, review decisions, and audit events.

- Preserve raw records, source IDs, provenance, and input hashes. Validate derived representations without rewriting source text.
- Validate record schemas and cross-record relationships, including citation prompt/engine consistency with its response.
- Safely reuse identical repeated imports; reject conflicting content under an existing ID.
- Return record-level errors and retain valid records. Records with missing dependencies remain rejected with explicit reasons.
- Keep citation occurrences intact. For unique-URL statistics, deduplicate exact URL strings within each response and disclose that rule.
- Treat text and markdown as representations of one response.

### Semantic analysis and scoring

Define a versioned classification contract containing mention, recommendation, negative characterization, competitors, observable position, supporting excerpts, and uncertainty.

Mention, recommendation, and negative characterization may overlap. Absence requires a successful judgment that the brand is not mentioned; processing failure is a separate status.

Use a versioned prompt that treats answers as untrusted evidence and requires structured JSON. Validate outputs and verify quoted excerpts against the archived answer. Excerpt matching confirms traceability, not semantic correctness.

Start with sequential execution, a 120-second per-attempt timeout, at most two attempts per response, and a 2,048-token output cap. Record every attempt, execution mode, model identifier, prompt version, duration, and validation failure. Reject oversized inputs explicitly rather than silently truncating them. Benchmark context requirements before the full run.

Use this initial, deliberately simple visibility rubric:

- Absent: **0**
- Mentioned without recommendation: **25**
- Recommended: **100**

Preserve negative characterization, recommendation position, and citation presence as separate components instead of hiding them inside the score. Explain that the score measures visibility and endorsement, not factual accuracy or business impact.

Aggregate successful classifications with equal response weights. Show successful, failed, skipped, and eligible counts beside every aggregate. Empty groups have no score. Compare engines on shared successfully analyzed prompts, and distinguish branded from unbranded questions. Freeze a small, documented prompt-category mapping before final evaluation.

### Reporting and review

Generate structured reports containing scores, coverage, exactly three diagnostics, and three prioritized remedies. Each diagnostic separates the observed pattern, possible explanation, and evidence needed to test it. Each remedy records evidence, action, expected benefit, effort, uncertainty, and a measurable validation step.

Use deterministic report assembly from validated observations; substantive LLM use occurs in classification. Analysts can revise narrative findings and remedies. Preserve original model results and computed scores. Record any classification correction separately with actor and reason, then recompute derived results.

Submitting freezes a report version. Decisions attach to that exact version. Editing submitted or approved content creates a new draft. Export defaults to the current version and refuses unapproved content; an explicitly requested older approved version remains exportable with its identity clearly displayed.

Configure separate analyst and reviewer bearer tokens through environment variables. Derive roles server-side. Persist reviewer comments, actors, timestamps, and decisions.

### API surface and execution

Provide:

- `POST /datasets` — import the configured input pack and return validation results.
- `POST /analyses`, `GET /analyses/{id}` — execute bounded analysis and inspect persisted results.
- `GET /reports/{id}`, `PATCH /reports/{id}` — inspect and revise a draft.
- `POST /reports/{id}/submit` — freeze the current version.
- `POST /reports/{id}/decision` — approve or reject an explicit submitted version.
- `GET /reports/{id}/export?version_id=...` — export approved JSON.
- `GET /health` and generated API documentation.

Use one application process and one analysis execution at a time. Persist each result independently; on restart, mark interrupted runs explicitly. Full resumability and distributed workers remain future work.

Use structured errors with request IDs and appropriate 401, 403, 404, 409, 422, and provider-failure responses. Keep credentials out of traces. Do not fetch arbitrary supplied URLs automatically.

## 3. Documentation and development records

Create the requested artifacts during implementation:

- **`SPEC.md`:** normative requirements, architecture, entity relationships, API contracts, rubric, model contract, failure behavior, permissions, and acceptance criteria. Assign requirement IDs and connect them to tests.
- **`IMPLEMENTATION_PLAN.md`:** execution phases, dependencies, deadlines, tasks, verification gates, and completion status. Link to explanations instead of duplicating them.
- **`docs/architecture-overview.md`:** component and review-lifecycle diagrams, with concrete examples.
- **`docs/data-pipeline.md`:** source fields, validation, evidence handling, classification, scoring arithmetic, and aggregation examples.
- **`docs/adr/`:** concise decisions covering framework/database, local model and adapter design, scoring, immutable review, and execution limits.
- **`docs/onboarding.md`:** verified Windows setup, environment configuration, database initialization, start/test/evaluation commands, and demonstration requests.
- **`journey/changelog.md`:** actual completed milestones.
- **`journey/dev-notes.md`:** dated work sessions, measured effort, experiments, failures, decisions, omissions, and remaining work.

Add a short README linking to onboarding and a submission decision note covering alternatives, results, limitations, AI assistance, and ownership. Clearly distinguish proposed commands from commands verified successfully.

## 4. Phased execution and verification gates

| Phase | Target window, IST | Tasks and dependencies | Definition of done |
|---|---|---|---|
| **0 — Specification and feasibility** | 28 Oct, approximately 10:20–11:30 p.m. | Establish documents and acceptance IDs; initialize project; inspect answer lengths; benchmark the installed model; select and label evaluation cases before tuning | Contracts recorded, local model produces validated sample output, measured runtime informs the full-run schedule |
| **1 — Import and persistence** | 28 Oct 11:30 p.m.–29 Oct 1:00 a.m. | Implement schema initialization, input validation, provenance storage, duplicate handling, and import API | Full pack imports; repeat import creates no duplicates; invalid records produce useful errors |
| **2 — Classification and scoring** | 29 Oct, 1:00–3:30 a.m. | Implement model adapter, output validation, traces, stubs, rubric, categories, and aggregates; start full local analysis as soon as the sample gate passes | Every response has a result or explicit failure/skipped reason; score arithmetic passes independent checks |
| **3 — Reports and review** | 29 Oct, 3:30–6:00 a.m. | Assemble reports; add draft edits, corrections, immutable submission, reviewer authorization, and export | Complete workflow succeeds; wrong-role, rejection, and stale-content exports are denied |
| **4 — Evaluation and integration** | 29 Oct, 6:00–9:00 a.m. | Run baseline comparison, held-out checks, evidence checks, failure tests, and full workflow tests; diagnose and fix an observed or controlled failure | Readable evaluation report exists; regression case passes; model limitations remain explicit |
| **5 — Reproducibility and handoff** | 29 Oct, 9:00 a.m.–1:00 p.m. | Complete docs, decision note, example requests, clean setup rehearsal, and final analysis artifact | Required deliverables are runnable and consistent; working version is frozen for review |
| **6 — Stabilization and demonstration** | 29 Oct, 1:00–7:00 p.m. | Fix defects, review code and decisions together, rehearse demonstration, verify private submission contents | Final checks pass; user can explain the flow, rubric, evidence limits, and failure/fix story |

Current phase status:

- **Phase 0 — complete with recorded model limitation:** evaluation labels, split protection, prompt
  categories, median feasibility evidence, and maximum-input benchmark are recorded. The maximum-input
  benchmark failed strict output validation and is not a quality result.
- **Phase 1 — complete:** full import, provider-provenance linkage, partial rejection, duplicate and
  conflict behavior, repeat-import row counts, and relationship checks have automated coverage.
- **Phase 2 — engineering complete; live full run blocked by quality evidence:** persistence,
  controlled stub/replay execution, APIs, terminal accounting, aggregates, explicit Ollama context
  control, provider diagnostics, and the Groq fallback adapter are implemented and tested. Local
  `gemma3:4b` failed the development reliability gate. Hosted `openai/gpt-oss-120b` with prompt v6
  passed all four development cases and is frozen by hashes. Its immutable held-out run validated
  5/8 cases and passed 4/8 exactly, including zero recall on the one positive recommendation case.
  This does not support accepting Groq for the full run. The request remains unexecuted and requires
  explicit approval even for a diagnostic run.
- **Phase 3 — complete:** deterministic report creation, evidence-linked immutable drafts,
  exact-version submission and decisions, reviewer authorization, rejection handling, and
  version-specific approved export are implemented and tested.
- **Phase 4 — in progress:** the frozen held-out evaluation is complete and documented; broader
  integration/evaluation artifacts remain. **Phase 5 — documentation partially updated. Phase 6 —
  not started.**

These are elapsed scheduling windows, not a requirement for uninterrupted human work. Log actual active effort separately. Protect the 1 p.m. checkpoint by dropping optional additions before reducing required tests or evaluation.

Implement a hosted adapter after the local workflow is stable, behind the same classification interface. Verify its contract using mocks. Live hosted evaluation requires approved access and remains separate from local results; it must not consume the stabilization buffer at the expense of core correctness.

## 5. Acceptance tests and completion criteria

Before tuning, manually label **12 supplied responses**, balanced across engines and spanning categories and available label cases. Use four for development and eight for the final check. Add two clearly marked synthetic edge cases. Version expected labels, evidence, selection rationale, and split membership.

One evaluation command must compare the rule baseline and local model on the same cases, report per-label precision/recall or agreement, show coverage and failures, independently check scores, and produce a readable report.

Required automated scenarios:

- Invalid schemas, broken references, identical duplicates, and conflicting IDs.
- Timeout, empty output, malformed JSON, invalid labels, and fabricated excerpts.
- Partial analysis failure without losing valid results.
- Wrong-role decisions, rejection blocking export, immutable submission, and edits requiring fresh approval.
- Explicit export of an older approved version without authorizing the new draft.
- Unsupported diagnostic claims and incorrect evidence links.
- Known scoring examples and aggregation denominators.
- A complete import-to-approved-export integration test.

Completion requires a full accepted-provider run accounting for all 150 responses, honest reporting of failures, three traceable diagnostics and remedies, passing required engineering tests, saved evaluation results, verified onboarding, and documented unresolved limitations. The accepted provider may be local or hosted but must first pass the frozen evaluation gates. No numerical model-quality threshold is invented; observed performance and concrete failures determine the claims made in the submission.
