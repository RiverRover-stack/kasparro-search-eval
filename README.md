# Kasparro AI Visibility Checker

A small program that checks how AI tools talk about one company, Kasparro, and makes sure a person
reviews the findings before anyone can use them.

## What is this, in one minute?

When people ask ChatGPT, Gemini or Google AI Mode for advice, do those tools mention Kasparro? Do they
recommend it? This project looks at 150 saved AI answers and finds out.

For each answer it records one of three things:

| What the answer did | Score |
|---|---|
| Did not mention Kasparro | 0 |
| Mentioned Kasparro | 25 |
| Recommended Kasparro | 100 |

Then it builds a report with **3 findings** and **3 suggested next steps**. A person edits the report.
A second person approves or rejects it. Only an approved report can be exported.

**The question it answers:** where does Kasparro seem to win or lose in AI answers, what proof is there,
and what should be checked or changed next?

## How it works

1. **Load the data.** 50 questions, each answered by 3 AI tools, gives 150 answers. The originals are
   never changed.
2. **Check each answer.** An AI model reads the answer and fills in a short form: was Kasparro
   mentioned, recommended, or criticised? A simple rule handles answers that do not contain the name.
3. **Score it.** Left out is 0, mentioned is 25, recommended is 100.
4. **Write the report.** 3 findings and 3 next steps, each linked to the answers that support it.
5. **Human review.** The analyst edits. The reviewer approves or rejects. Each edit makes a new version,
   and the reviewer approves one exact version. Nothing unapproved can be exported.

## Why you can trust the process

- **A failed check is never counted as zero.** If the AI model breaks, the answer shows as "failed", not
  "Kasparro was absent".
- **Quotes must be exact.** Any quote the model gives must appear word for word in the original answer.
  If not, the result is thrown out.
- **The model's answer is only a suggestion.** A person reviews it before anything is exported.
- **Roles are enforced by secret keys on the server.** Typing "I am the reviewer" does nothing.
- **Every number shows its totals.** An average always comes with how many answers succeeded, failed or
  were skipped.
- **The final test cases were locked.** Eight test answers were set aside and not used to tune the model or
  the prompt, so the final check is fair. One of them, the longest answer, was only used to check whether a
  small local model could read it at all (see `evaluation/benchmark-results.md`).

## What it does not claim

- It does not say Kasparro is good or bad. It measures how AI answers *talk* about it.
- It is a snapshot from one day (31 July 2026, India, English), not today's AI answers.
- The score does not predict traffic, sales or rankings.
- An exact quote proves the words are real. It does not prove the AI understood them.

## Results so far

| Check | Result |
|---|---|
| Automated tests | 151 pass |
| AI model on the 8 locked test cases | 5 gave a valid answer, 4 were fully correct, 3 failed to produce a valid answer. It missed the one "recommended" case. |
| A simple keyword rule on the same 8 cases | 4 fully correct. It ties the model on this count, but it is weaker at spotting criticism. |
| Score arithmetic | 28 checks, no mistakes |
| Live run over all 150 answers | 78 handled by the keyword rule. 39 sent to the AI model: 27 valid, 12 failed. 33 skipped on purpose. Every answer is accounted for. |
| What the model found (27 valid) | Kasparro was mentioned but not recommended in 26, recommended in 1. Criticised in 11. |
| How often the name appears (all 150) | ChatGPT 25 of 50, Google AI Mode 25 of 50, Gemini 22 of 50 |

Eight cases is a small test. These numbers come from one run and should be read as a first look, not a
final verdict.

## Where things stand

**Done**
- Loading and checking the data, safely and without duplicates.
- Scoring and the three-state result for every answer.
- Report versions, editing, review, and approved-only export.
- A test that compares the AI model with the simple keyword rule.

- Setup notes in `.env.example`, and a copy-paste walk-through of the whole review flow (see "Try the
  whole review flow"). It was run for real on 2026-10-29 against a local server in stub mode with a
  throw-away database. The two steps that should fail did: export before approval gave 409, and the
  analyst trying to approve gave 403.
- `evaluation/analysis-output.json` (scores with coverage, 3 findings, 3 next steps, open problems) and
  `docs/decision-note.md`.

- A live run of the AI model on a sample of 39 answers. The free plan's daily limit is too small for all
  150, so the other answers are marked "skipped" with a reason. 12 of the 39 failed because the model
  did not follow the required answer format. Failures are shown, never counted as zero.

- A report writer that uses the real results. It shows how often the name appears (all 150 answers)
  apart from what the AI model found, with the failed and skipped counts next to each number. The report no longer repeats the blended average.

**In progress**
- Nothing is running.

**Not done yet**
- Known problems that remain are listed in `evaluation/analysis-output.json` under `known_issues`.
  The main one: 5 of the 30 prompts marked "branded" do not contain the name Kasparro. The second finding
  now cites only prompts that do, and says so (see `docs/decision-note.md`).
- Counting unique links in answers.
- Resuming an analysis that stopped halfway.

## Try it

You need Python 3.10 or newer, and the supplied assignment pack (`data/`, `provenance/`, `reference/`,
`schemas/`, `fixtures/`, `PACK_MANIFEST.json`). The pack is not published in this repository: copy it into
this folder first. `py -3 tools\check_pack.py` tells you if anything is missing or changed.

In PowerShell, from this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -e ".[dev]"
py -3 tools\check_pack.py        # checks the input data is intact
py -3 -m pytest -q               # runs all tests, no internet needed
py -3 tools\run_evaluation.py    # model vs keyword rule comparison, no internet needed
py -3 tools\make_comparison_pdf.py     # the same comparison as a PDF with charts (needs the optional report packages)
py -3 tools\export_analysis_output.py   # rebuilds evaluation/analysis-output.json from the saved live-run
                                         # database (backend\live-run.db, not in Git); will not overwrite a file
```

To start the web service and see its documentation page:

```powershell
$env:KASPARRO_ANALYST_TOKEN = "choose-a-secret"
$env:KASPARRO_REVIEWER_TOKEN = "choose-another-secret"
py -3 -m uvicorn backend.app.main:app
```

Then open `http://127.0.0.1:8000/docs`. More notes are in [`docs/onboarding.md`](docs/onboarding.md).

Exact package versions the project was tested with are in `requirements-tested.txt`. The PDF report needs two
extra packages: `py -3 -m pip install -e ".[report]"`.

### No key needed, and the real model

Set `execution_mode` in the analysis request.

- `stub`: no model and no internet. It proves the app works (import, scoring, review, export). It says
  nothing about model quality.
- `replay`: plays back saved model answers sent in the request. `py -3 tools\run_evaluation.py` does the
  same with the saved real-model results in `evaluation/`, with no internet and no key. Model-quality
  numbers from it are single-run and unverified.
- `hosted_groq`: the real model. Put `GROQ_API_KEY=...` and `KASPARRO_GROQ_MODEL=openai/gpt-oss-120b` in
  `.env`. Without the key the API returns 422; it never switches model on its own.
  `py -3 tools\run_live_analysis.py` only prints a plan. Sending needs `--confirm-send`, and the
  recorded run took about 35 minutes (2,104 s) because of the free plan's limits (see `docs/onboarding.md`).
- `local_ollama`: a local model (`gemma3:4b`). Download it first with `ollama pull gemma3:4b`; it is a few
  gigabytes, so the time depends on your connection. It failed the development checks, so it is not the
  evaluated model.

**Replay request.** `replay_results` maps a response ID (from `data/responses.jsonl`) to one saved result.
Any response without an entry is recorded as `failed`, never as brand absence.

```json
{
  "dataset_id": "<id from POST /datasets>",
  "execution_mode": "replay",
  "replay_results": {
    "<response_id>": {
      "contract_version": "classification-v1",
      "brand_mentioned": false,
      "recommended": false,
      "negative_characterization": false,
      "competitors": [],
      "observable_position": null,
      "supporting_excerpts": [],
      "uncertainty": "low",
      "uncertainty_reason": "Kasparro is not named in this answer."
    }
  }
}
```

**Database.** There is no separate setup step. The SQLite file (default `backend/kasparro.db`; change it
with `KASPARRO_DATABASE_URL`) and its tables are created the first time the server starts
(`initialize_database()` in `backend/app/database.py`). `POST /datasets` then loads the pack into it.

**How long setup takes.** Creating the venv, installing, `check_pack.py` and the tests took a few minutes in
the author's runs (the test suite itself about 25 seconds). It has not been timed from a cold start. Stub and
replay need no download. Only `local_ollama` needs a model download (see above). The Groq live sample is
the long step (about 35 minutes), and it is optional.

**Controlled fixture.** The deterministic `ControlledStubClassifier` (the `stub` mode) is the controlled
fixture for the engineering tests. The two clearly marked synthetic edge cases are in
`evaluation/labels-v1.json` under `synthetic_cases`. The supplied `fixtures/failure_scenarios.json` is not
used by the tests.

Instead of typing the two secrets each time, you can copy `.env.example` to `.env` and fill them in.
`.env` is never committed. `.env.example` lists every setting, with the secrets left blank.

## Try the whole review flow

This walk-through uses the built-in **stub** mode. It sends nothing over the internet and needs no AI
key. The stub gives made-up results, so it only shows that the steps work. It does not show how good the
model is.

**Window 1.** Start the server with two secrets of your choice. Use a throw-away database file so you do
not touch your real one.

```powershell
$env:KASPARRO_ANALYST_TOKEN = "choose-a-secret"
$env:KASPARRO_REVIEWER_TOKEN = "choose-another-secret"
$env:KASPARRO_DATABASE_URL = "sqlite:///backend/demo.db"
py -3 -m uvicorn backend.app.main:app
```

**Window 2.** Set the same two secrets, then run the steps below one block at a time, from this folder.

```powershell
$env:KASPARRO_ANALYST_TOKEN = "choose-a-secret"
$env:KASPARRO_REVIEWER_TOKEN = "choose-another-secret"
$base = "http://127.0.0.1:8000"
$analyst = @{ Authorization = "Bearer $env:KASPARRO_ANALYST_TOKEN" }
$reviewer = @{ Authorization = "Bearer $env:KASPARRO_REVIEWER_TOKEN" }
$json = "application/json"

# 1. Load the 150 answers (analyst only).
$dataset = Invoke-RestMethod -Method Post -Headers $analyst "$base/datasets"

# 2. Check every answer. "stub" means no model and no internet.
$body = @{ dataset_id = $dataset.dataset_id; execution_mode = "stub" } | ConvertTo-Json
$analysis = Invoke-RestMethod -Method Post -Headers $analyst -ContentType $json -Body $body "$base/analyses"

# 3. Build the report. It starts as version 1, a draft.
$body = @{ analysis_id = $analysis.analysis_id } | ConvertTo-Json
$report = Invoke-RestMethod -Method Post -Headers $analyst -ContentType $json -Body $body "$base/reports"
$id = $report.report_id

# 4. The analyst submits version 1. Submitting freezes it.
$body = @{ version_id = $report.current_version_id } | ConvertTo-Json
$report = Invoke-RestMethod -Method Post -Headers $analyst -ContentType $json -Body $body "$base/reports/$id/submit"

# 5. Nobody can export yet. This should fail with 409.
try { Invoke-RestMethod -Headers $analyst "$base/reports/$id/export" } catch { $_.Exception.Response.StatusCode.value__ }

# 6. The reviewer rejects version 1. A comment is required.
$body = @{ version_id = $report.current_version_id; decision = "rejected"; comment = "Please check the wording." } | ConvertTo-Json
$report = Invoke-RestMethod -Method Post -Headers $reviewer -ContentType $json -Body $body "$base/reports/$id/decision"

# 7. The analyst edits. This makes version 2, a new draft. Version 1 stays as it was.
$content = $report.current_version.content
$content.diagnostics[0].possible_explanation += " Wording checked against the answers."
$body = @{ content = $content } | ConvertTo-Json -Depth 20
$report = Invoke-RestMethod -Method Patch -Headers $analyst -ContentType $json -Body $body "$base/reports/$id"

# 8. The analyst submits version 2.
$body = @{ version_id = $report.current_version_id } | ConvertTo-Json
$report = Invoke-RestMethod -Method Post -Headers $analyst -ContentType $json -Body $body "$base/reports/$id/submit"

# 9. Wrong role: the analyst tries to approve. This should fail with 403.
$body = @{ version_id = $report.current_version_id; decision = "approved"; comment = "I approve my own work." } | ConvertTo-Json
try { Invoke-RestMethod -Method Post -Headers $analyst -ContentType $json -Body $body "$base/reports/$id/decision" } catch { $_.Exception.Response.StatusCode.value__ }

# 10. The reviewer approves version 2.
$body = @{ version_id = $report.current_version_id; decision = "approved"; comment = "Evidence checked." } | ConvertTo-Json
$report = Invoke-RestMethod -Method Post -Headers $reviewer -ContentType $json -Body $body "$base/reports/$id/decision"

# 11. Now the approved version can be exported.
Invoke-RestMethod -Headers $analyst "$base/reports/$id/export" | ConvertTo-Json -Depth 20
```

Each edit makes a new version, and a decision belongs to one exact version. If you edit again after
approval, the new draft cannot be exported until it is submitted and approved too. Press Ctrl+C in
window 1 to stop the server.

## Built with AI help

This project was built with an AI coding assistant (Claude Code) under a person's direction. Every
change was reviewed and approved by that person, and every claim above was checked against the code and
test results.

## Learn more

- [`SPEC.md`](SPEC.md): exactly what the system does, in plain language.
- [`docs/adr/`](docs/adr/): the reasons behind the main design choices.
- [`docs/decision-note.md`](docs/decision-note.md): the main choices, the biggest risks and what was left out.
- [`evaluation/analysis-output.json`](evaluation/analysis-output.json): the live-run numbers, findings and open problems.
- [`evaluation/comparison-report.md`](evaluation/comparison-report.md): the full model-versus-rule results.
- [`evaluation/comparison-report.pdf`](evaluation/comparison-report.pdf): the same results as a PDF with charts and
  confusion matrices.
