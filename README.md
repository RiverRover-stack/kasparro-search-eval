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
- **The final test cases were locked.** Eight test answers were set aside and never used to improve the
  model, so the final check is fair.

## What it does not claim

- It does not say Kasparro is good or bad. It measures how AI answers *talk* about it.
- It is a snapshot from one day (31 July 2026, India, English), not today's AI answers.
- The score does not predict traffic, sales or rankings.
- An exact quote proves the words are real. It does not prove the AI understood them.

## Results so far

| Check | Result |
|---|---|
| Automated tests | 94 pass |
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

- A live run of the AI model on a sample of 39 answers. The free plan's daily limit is too small for all
  150, so the other answers are marked "skipped" with a reason. 12 of the 39 failed because the model
  did not follow the required answer format. Failures are shown, never counted as zero.

**In progress**
- Nothing is running. The next step is a report writer that says where Kasparro wins or loses.

**Not done yet**
- The report writer is basic. It describes how the analysis went but does not yet say where Kasparro wins
  or loses. Fixing this is the next planned step.
- Counting unique links in answers.
- Resuming an analysis that stopped halfway.

## Try it

You need Python 3.10 or newer. In PowerShell, from this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -e ".[dev]"
py -3 tools\check_pack.py        # checks the input data is intact
py -3 -m pytest -q               # runs all tests, no internet needed
py -3 tools\run_evaluation.py    # model vs keyword rule comparison, no internet needed
```

To start the web service and see its documentation page:

```powershell
$env:KASPARRO_ANALYST_TOKEN = "choose-a-secret"
$env:KASPARRO_REVIEWER_TOKEN = "choose-another-secret"
py -3 -m uvicorn backend.app.main:app
```

Then open `http://127.0.0.1:8000/docs`. Step by step request examples are in
[`docs/onboarding.md`](docs/onboarding.md).

## Built with AI help

This project was built with an AI coding assistant (Claude Code) under a person's direction. Every
change was reviewed and approved by that person, and every claim above was checked against the code and
test results.

## Learn more

- [`SPEC.md`](SPEC.md): exactly what the system does, in plain language.
- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md): what is finished and what is left.
- [`docs/adr/`](docs/adr/): the reasons behind the main design choices.
- [`journey/`](journey/): dated notes on how the project developed, including what went wrong.
- [`evaluation/comparison-report.md`](evaluation/comparison-report.md): the full model-versus-rule results.
