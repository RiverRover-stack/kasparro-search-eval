# Onboarding

## Environment

Verified on Windows with Python 3.13.1. The project supports Python 3.10 or newer. The initial
environment had FastAPI 0.128.0, Pydantic 2.13.4, SQLAlchemy 2.0.46, Uvicorn 0.40.0, HTTPX 0.28.1,
and pytest 9.0.3 installed. `gemma3:4b` was present in Ollama. A 4,507-character classification
sample validated on its second bounded attempt after a deterministic mention guard was added; the
two attempts took 30.4 and 9.5 seconds. This is one feasibility measurement, not a quality claim.

## Setup and checks

Verified commands:

```powershell
py -3 tools\check_pack.py
py -3 -m pytest
```

Proposed clean-environment setup and server commands (to be rehearsed in Phase 5):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -e ".[dev]"
$env:KASPARRO_DATABASE_URL = "sqlite:///backend/kasparro.db"
py -3 -m uvicorn backend.app.main:app --reload
```

The default input pack is the project root. Override it with `KASPARRO_INPUT_PACK`. The default
database is `backend/kasparro.db`; override it with `KASPARRO_DATABASE_URL`.

## Demonstration requests

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post http://127.0.0.1:8000/datasets
$dataset = Invoke-RestMethod -Method Post http://127.0.0.1:8000/datasets
$body = @{ dataset_id = $dataset.dataset_id; execution_mode = "stub" } | ConvertTo-Json
$analysis = Invoke-RestMethod -Method Post -ContentType "application/json" -Body $body http://127.0.0.1:8000/analyses
Invoke-RestMethod "http://127.0.0.1:8000/analyses/$($analysis.analysis_id)"
```

Swagger UI is available at `http://127.0.0.1:8000/docs`.

The live HTTP path was verified on port 8765 during development: `/health` returned 200 with an
`X-Request-ID`, OpenAPI listed `/health` and `/datasets`, the pack import accepted all source rows,
and the second import returned the same dataset ID with `reused: true`.

The analysis commands above use the controlled stub. This HTTP path was verified on port 8766 with an
isolated database: import linked 150 provenance records, `POST /analyses` returned a completed run with
150 successful terminal results, `GET /analyses/{id}` returned the same run, and the shared comparison
contained 50 prompts. Stub results verify persistence, failure accounting, scoring, and API shape; they
are not evidence of local-model quality. Use `execution_mode = "local_ollama"` only when Ollama is
running and enough time is available for bounded sequential processing.

