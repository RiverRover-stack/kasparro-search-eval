# Kasparro Visibility Backend Specification

Status: implementation baseline, 28 October 2026.

The system imports the supplied historical capture, classifies each archived answer through a
bounded model adapter, computes transparent visibility scores, and moves evidence-linked reports
through analyst and reviewer controls. Raw evidence and model outputs are never silently rewritten.

## Requirements

- **DATA-001:** Preserve source IDs, raw records, provenance, and content hashes.
- **DATA-002:** Validate record schemas plus prompt/response/citation relationships. Retain valid
  records and return record-level reasons for rejected records.
- **DATA-003:** Reuse an identical run import without duplicates; reject different content under an
  existing run ID.
- **DATA-004:** Preserve citation occurrences. Any unique-URL statistic deduplicates exact URL
  strings within one response and discloses that rule.
- **CLS-001:** Classification contract version 1 records mention, recommendation, negative
  characterization, competitors, observable position, supporting excerpts, and uncertainty.
- **CLS-002:** A processing failure is not an observation of brand absence.
- **CLS-003:** Model attempts are bounded to 120 seconds, two attempts, and 2,048 output tokens;
  oversized inputs are explicitly skipped.
- **CLS-004:** Supporting excerpts must occur verbatim in the archived answer. This confirms
  traceability, not semantic correctness.
- **SCORE-001:** Absent scores 0, mentioned without recommendation scores 25, and recommended
  scores 100. Negative characterization, position, and citation presence remain separate.
- **SCORE-002:** Aggregates show successful, failed, skipped, and eligible counts. Empty groups have
  no score; engine comparisons use shared successfully analysed prompts.
- **REPORT-001:** A report has exactly three diagnostics and three remedies with linked evidence,
  uncertainty, and measurable validation steps.
- **REVIEW-001:** Submission freezes a version. Decisions bind to that exact submitted version;
  later edits create a new draft.
- **REVIEW-002:** Only the configured reviewer role may decide. Unapproved versions cannot export;
  an explicitly selected older approved version remains exportable.
- **API-001:** The API exposes the endpoints in `IMPLEMENTATION_PLAN.md` and generated OpenAPI docs.
- **API-002:** Errors include a stable code and request ID and use appropriate HTTP status codes.
- **OPS-001:** One application process performs at most one analysis at a time. Restart marks an
  interrupted run explicitly.
- **SEC-001:** Roles come from separate environment-provided bearer tokens. Credentials never enter
  traces, audit details, or exported reports.

## Implemented acceptance mapping

| Requirement | Current automated evidence |
|---|---|
| DATA-001 | `tests/test_importer.py::test_full_pack_import_is_lossless_and_idempotent` |
| DATA-002 | `tests/test_importer.py::test_missing_dependency_rejects_response_and_citation` |
| DATA-003 | `tests/test_importer.py::test_full_pack_import_is_lossless_and_idempotent` |
| DATA-001 provenance linkage | `tests/test_importer.py::test_full_pack_import_is_lossless_and_idempotent` |
| DATA-002 invalid/duplicate/relationship cases | `tests/test_importer.py` schema, duplicate, dependency, and parent-mismatch tests |
| DATA-003 changed source run | `tests/test_importer.py::test_changed_content_under_existing_run_id_conflicts` |
| CLS-001 | `tests/test_classification.py` contract validation tests |
| CLS-002 | `tests/test_analysis.py::test_partial_failure_and_oversized_input_keep_valid_results` |
| CLS-003 | `tests/test_classification.py` timeout, malformed-output, and oversized-input tests |
| CLS-004 | `tests/test_classification.py::test_fabricated_excerpt_is_rejected` |
| SCORE-001 | `tests/test_classification.py::test_visibility_score` |
| SCORE-002 | `tests/test_analysis.py::test_stub_analysis_persists_terminal_results_and_aggregates` |
| API-001 | `tests/test_health.py::test_openapi_documents_dataset_import` |
| API-002 | Request-ID middleware implemented; live HTTP verification recorded in dev notes |

Requirements not listed in the table remain planned rather than implemented.

## Implemented analysis API contract

`POST /analyses` accepts a dataset ID and an execution mode of `stub`, `replay`, or `local_ollama`.
The controlled stub is deterministic engineering evidence only. Replay accepts explicitly supplied,
contract-valid classifications keyed by response ID; a missing replay item becomes a failed response,
not absence. Local execution uses the bounded adapter. `GET /analyses/{id}` returns the persisted run,
per-response terminal states, separate classification fields, citation presence, denominated totals,
per-engine aggregates, and comparisons restricted to prompts successfully analyzed by every engine.

Every eligible response is `successful`, `failed`, or `skipped` with a reason. Oversized inputs are
skipped before adapter invocation and are never truncated. Attempts store duration, execution mode,
model identifier, prompt version, raw output, and validation failure. Runs left `running` across an
application restart are marked `interrupted` during startup.

