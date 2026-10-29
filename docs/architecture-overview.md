# Architecture overview

The backend keeps source evidence, semantic classification, deterministic scoring, and human review
as separate layers. Imported prompts, responses, citations, and provider provenance are immutable
inputs. An analysis run records every classifier attempt and gives each response one terminal state:
successful, failed, or skipped. Only successful classifications contribute to scores.

```text
input pack -> validated source records -> bounded classifier attempts
           -> terminal response results -> deterministic aggregates
           -> report draft v1 -> submitted v1 -> reviewer decision on v1 -> approved export v1
                                  |
                                  +-> analyst edit -> draft v2 -> fresh review required
```

A run can mix classifiers. A literal rule handles answers that do not contain the brand name, a hosted
model handles a fixed sample of the rest, and every other response is skipped with a reason. A provider
daily-quota error stops the run as `interrupted` and no report can be built from it. Each attempt records
its own execution mode.

Reports do not rewrite analysis results. A report version stores a content hash, summary, exactly
three diagnostics, and exactly three remedies. Separate evidence-link rows connect every diagnostic
and remedy to persisted response results from the same analysis. Diagnostic explanations are labeled
as hypotheses and include the evidence needed to test them.

Submission changes only lifecycle state; it does not modify content. A reviewer decision belongs to
one submitted version. Editing any draft, submitted, rejected, or approved report creates a new draft
version. Default export selects the current version and rejects it unless approved. Supplying an older
approved `version_id` exports that version without granting approval to a newer draft.

The API derives analyst and reviewer roles from separate environment-configured bearer tokens.
Tokens are compared server-side and never enter report content, audit details, model traces, or
exports. Audit events record report creation, edits, submission, decisions, and exports using role
identities rather than credential values.
