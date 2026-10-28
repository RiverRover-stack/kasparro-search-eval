# ADR 0005: Immutable report versions and exact-version review

Status: accepted, 29 October 2026.

## Decision

Store every report edit as a new version with a canonical SHA-256 content hash. Submission freezes the
current draft. Approval or rejection is a separate record bound to that submitted version. Evidence
links are normalized rows from report sections to response-classification results in the same
analysis. Default export considers only the current version; callers may explicitly export an older
approved version.

Analyst and reviewer permissions use separate environment-provided bearer tokens. The server derives
the role and stores only the role name in review and audit records.

## Consequences

Reviewed content cannot be changed under an existing approval. Corrections require a new draft and a
fresh decision, while an older approved artifact remains reproducible. The initial bearer-token model
is intentionally small and local; production deployment would replace it with an identity provider
without changing the version and decision rules.
