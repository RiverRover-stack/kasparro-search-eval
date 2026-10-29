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

Local Ollama defaults to a project-requested 16,384-token context. Override it with
`KASPARRO_OLLAMA_CONTEXT_TOKENS`. The local 4B model is retained for reproducibility but has not passed
the development reliability gate.

The root `.env` file is loaded automatically by `backend/app/config.py` and is ignored by Git. Add the
key to that local file:

```powershell
GROQ_API_KEY=<your local secret>
KASPARRO_GROQ_MODEL=openai/gpt-oss-120b
KASPARRO_ANALYST_TOKEN=<separate analyst bearer token>
KASPARRO_REVIEWER_TOKEN=<separate reviewer bearer token>
```

Process-level environment variables override `.env`, allowing deployment configuration without file
changes. The loader supports comments, `export KEY=VALUE`, and single- or double-quoted values; invalid
entries stop startup with their line number. Do not add the key to source files, requests, screenshots,
or development notes. Use `execution_mode = "hosted_groq"` in the analysis request. Without the key,
the API returns 422 rather than silently falling back to another provider.

## Frozen hosted evaluation

Save and pass the four development cases before touching the held-out runner:

```powershell
py -3 tools\benchmark_development.py --provider groq > evaluation\groq-development-120b.json
py -3 tools\freeze_hosted_evaluation.py
```

The freeze command requires four validated, passing development cases on the configured model. It
records hashes for the development artifact, classifier source, label set, and held-out runner without
recording the API key. It refuses to overwrite an existing freeze manifest.

The final held-out artifacts now exist and are immutable. Do not run this command again or overwrite
them. For a fresh project freeze only, the one-time command would be:

```powershell
py -3 tools\benchmark_held_out.py --confirm-frozen
```

The runner verifies all frozen hashes before sending a request, waits 30 seconds between cases to
reduce token-per-minute failures, and refuses to overwrite existing held-out evidence. It writes
`evaluation/groq-held-out-120b.json` and `evaluation/groq-held-out-120b.md`. A nonzero exit code is an
evaluation result to document, not permission to tune against the held-out cases.

The recorded held-out run validated 5/8 cases and passed 4/8 exactly. Recommendation recall was 0 for
the one positive case, two cases exhausted retries on provider schema rejection, and one exhausted
retries on local contract validation. Groq is therefore not accepted for the full run.

## Full hosted-run readiness

The free plan allows 8,000 tokens per minute and 200,000 per day, so all 150 answers cannot be sent in one
day. The supported path is a mixed run on a fixed sample: answers without the brand name are handled by a
rule, 39 mention answers (13 per engine) go to Groq, and the rest are skipped with a reason. First print
the plan, which sends nothing:

```powershell
py -3 tools\run_live_analysis.py
```

Sending needs your explicit approval, because 39 archived answers leave the machine. Use a fresh database;
the old `backend/kasparro.db` refuses the pack import (probably created before the pack hash included
provenance):

```powershell
py -3 tools\run_live_analysis.py --confirm-send --database-url sqlite:///backend/live-run.db
```

It prints nothing for about 35 minutes, then a summary, and writes `evaluation/live-run-groq-sample.json`
(it will not overwrite an existing file). A daily-quota error stops the run as `interrupted`. The older
single-request path below sends the whole dataset in one HTTP call and is not suitable for the free plan.

```powershell
$analystHeaders = @{ Authorization = "Bearer $env:KASPARRO_ANALYST_TOKEN" }
$dataset = Invoke-RestMethod -Method Post -Headers $analystHeaders http://127.0.0.1:8000/datasets
$body = @{ dataset_id = $dataset.dataset_id; execution_mode = "hosted_groq" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Headers $analystHeaders -ContentType "application/json" -Body $body http://127.0.0.1:8000/analyses
```

Importing and analysing require the analyst token; a reviewer token gets `403`.

The current API runs sequentially in the request process, and the adapter honors provider rate-limit
waits and bounded retries. The HTTP request may therefore remain open for a long time. A background
worker is production hardening for Phase 6, not part of this local assignment workflow.

## Demonstration requests

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
$analystHeaders = @{ Authorization = "Bearer $env:KASPARRO_ANALYST_TOKEN" }
$dataset = Invoke-RestMethod -Method Post -Headers $analystHeaders http://127.0.0.1:8000/datasets
$dataset = Invoke-RestMethod -Method Post -Headers $analystHeaders http://127.0.0.1:8000/datasets
$body = @{ dataset_id = $dataset.dataset_id; execution_mode = "stub" } | ConvertTo-Json
$analysis = Invoke-RestMethod -Method Post -Headers $analystHeaders -ContentType "application/json" -Body $body http://127.0.0.1:8000/analyses
Invoke-RestMethod "http://127.0.0.1:8000/analyses/$($analysis.analysis_id)"
```

Report lifecycle requests use separate bearer tokens. The example below uses the controlled stub and
PowerShell variables; do not paste real tokens into tracked files or logs.

```powershell
$analystHeaders = @{ Authorization = "Bearer $env:KASPARRO_ANALYST_TOKEN" }
$reviewerHeaders = @{ Authorization = "Bearer $env:KASPARRO_REVIEWER_TOKEN" }
$reportBody = @{ analysis_id = $analysis.analysis_id } | ConvertTo-Json
$report = Invoke-RestMethod -Method Post -Headers $analystHeaders -ContentType "application/json" -Body $reportBody http://127.0.0.1:8000/reports
$submitBody = @{ version_id = $report.current_version_id } | ConvertTo-Json
$submitted = Invoke-RestMethod -Method Post -Headers $analystHeaders -ContentType "application/json" -Body $submitBody "http://127.0.0.1:8000/reports/$($report.report_id)/submit"
$decisionBody = @{ version_id = $submitted.current_version_id; decision = "approved"; comment = "Evidence reviewed." } | ConvertTo-Json
Invoke-RestMethod -Method Post -Headers $reviewerHeaders -ContentType "application/json" -Body $decisionBody "http://127.0.0.1:8000/reports/$($report.report_id)/decision"
Invoke-RestMethod -Headers $analystHeaders "http://127.0.0.1:8000/reports/$($report.report_id)/export"
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

