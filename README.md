# Kasparro Visibility Backend

This project implements the local, evidence-linked workflow described in
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). The supplied assignment inputs remain at
the repository root and are imported without rewriting their source records.

Current implementation status: lossless/idempotent import, queryable provider provenance, bounded
classification contracts, analysis persistence, controlled stub/replay execution, analysis APIs,
transparent aggregates, and the evidence-linked report/review/export lifecycle are implemented.

The local `gemma3:4b` feasibility adapter did not pass the frozen development reliability gate. A Groq
strict-structured-output fallback passed development 4/4 but only validated 5/8 and passed 4/8 on the
immutable held-out set. It is not accepted for the full run, which has not been executed.

Local configuration is read automatically from the Git-ignored root `.env`; process environment
variables take precedence. Leave `GROQ_API_KEY` blank until a real key is configured locally.

## Local verification

These commands are intended for Windows PowerShell from the project root:

```powershell
py -3 tools\check_pack.py
py -3 -m pytest
$env:KASPARRO_DATABASE_URL = "sqlite:///backend/kasparro.db"
py -3 -m uvicorn backend.app.main:app --reload
```

After startup, open `http://127.0.0.1:8000/docs`, call `GET /health`, then call
`POST /datasets`. A second identical import reuses the existing dataset.

See [`SPEC.md`](SPEC.md) for requirement IDs and [`docs/onboarding.md`](docs/onboarding.md)
for environment details and verified-versus-proposed commands.

