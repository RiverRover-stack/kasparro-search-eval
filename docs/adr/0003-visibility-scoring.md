# ADR 0003: Deliberately simple visibility scoring

Status: accepted, 28 October 2026.

Use 0 for absence, 25 for mention without recommendation, and 100 for recommendation. The score
measures visibility and endorsement, not accuracy or business impact. Negative characterization,
position, citation presence, uncertainty, and coverage remain separate fields. This avoids hiding
meaningful evidence inside one composite number and keeps arithmetic independently testable.

