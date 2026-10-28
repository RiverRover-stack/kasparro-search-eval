# ADR 0001: FastAPI, Pydantic, SQLAlchemy, and SQLite

Status: accepted, 28 October 2026.

Use FastAPI for explicit REST contracts and generated OpenAPI, Pydantic for boundary validation,
SQLAlchemy for persistence contracts, and SQLite for a reproducible single-process local workflow.
This combination matches the assignment constraints and leaves the service interface testable.
Distributed execution and a hosted database are deliberately outside the required build.

