# Kasparro AI visibility classifier: model versus keyword baseline

Evaluation comparison report. Label set: visibility-evaluation-v1.

This report compares one frozen language model run (openai/gpt-oss-120b via Groq) with a simple keyword baseline on the same labelled cases. Both are scored against the project owner's labels for four fields of each archived AI answer. It is written for a reviewer who has not seen the project. Nothing here is run over the network; the model results are read from saved files.

Caveat: single frozen model run, owner-written labels, model quality unverified.

## Headline results (held-out set, 8 cases)

| System | Valid results | Coverage | Exact-match cases | brand_mentioned agreement | recommended agreement | negative_characterization agreement |
|---|---:|---:|---:|---:|---:|---:|
| Model (one recorded run; repeatability not tested) | 5/8 | 62.5% | 4/8 | 0.625 | 0.500 | 0.625 |
| Keyword baseline | 8/8 | 100.0% | 4/8 | 1.000 | 0.875 | 0.500 |

Agreement is counted over all cases in the set, so a failed model result lowers the model's agreement.

## How to read the metrics

- Agreement = (TP + TN) / all cases in the set. A failed result counts as not agreeing.
- Precision = TP / (TP + FP). Recall = TP / (TP + FN). Both show n/a when the denominator is zero.
- TP, FP, FN, TN compare the owner's label (Actual) with the system's answer (Predicted). TP = both yes; FP = system yes, owner no; FN = system no, owner yes; TN = both no.
- Coverage = validated results / total cases. A result is validated when the model output passed the contract check.
- Exact match = all four fields correct for a case.
- observable_position is graded by exact equality with the owner's label, not by precision and recall.
- Failed results are not counted as absence: they are left out of TP, FP, FN and TN.

## Held-out final check (8 cases)

- Baseline: rules baseline (tools/rule_baseline.py), no model.
- Model: frozen hosted_groq artifact (openai/gpt-oss-120b), read from evaluation/, not rerun. The model was not run on the synthetic cases.

### Model (one recorded run; repeatability not tested)

- Execution mode: frozen hosted_groq artifact (openai/gpt-oss-120b), read from evaluation/, not rerun
- Coverage (validated/total): 5/8
- Exact passes (all four fields): 4/8

| Label | Agreement | Precision | Recall | TP | FP | FN | TN |
|---|---:|---:|---:|---:|---:|---:|---:|
| brand_mentioned | 0.625 | 1.000 | 1.000 | 3 | 0 | 0 | 2 |
| recommended | 0.500 | n/a | 0.000 | 0 | 0 | 1 | 4 |
| negative_characterization | 0.625 | 1.000 | 1.000 | 2 | 0 | 0 | 3 |
| observable_position | 0.625 | n/a | n/a | - | - | - | - |

observable_position is graded by exact equality: 5 of 8 cases matched.

### Baseline

- Execution mode: rules baseline (tools/rule_baseline.py), no model
- Coverage (validated/total): 8/8
- Exact passes (all four fields): 4/8

| Label | Agreement | Precision | Recall | TP | FP | FN | TN |
|---|---:|---:|---:|---:|---:|---:|---:|
| brand_mentioned | 1.000 | 1.000 | 1.000 | 5 | 0 | 0 | 3 |
| recommended | 0.875 | n/a | 0.000 | 0 | 0 | 1 | 7 |
| negative_characterization | 0.500 | 0.000 | 0.000 | 0 | 1 | 3 | 4 |
| observable_position | 1.000 | n/a | n/a | - | - | - | - |

observable_position is graded by exact equality: 8 of 8 cases matched.

### Confusion matrices

Rows are the owner's label (Actual), columns are the system's answer (Predicted). Failed model cases are excluded from the model matrices, so they cover 5 of 8 cases; the baseline covers all 8.

**brand_mentioned**

| Actual | Model predicted yes | Model predicted no | Baseline predicted yes | Baseline predicted no |
|---|---:|---:|---:|---:|
| Actual yes | 3 | 0 | 5 | 0 |
| Actual no | 0 | 2 | 0 | 3 |

**recommended**

| Actual | Model predicted yes | Model predicted no | Baseline predicted yes | Baseline predicted no |
|---|---:|---:|---:|---:|
| Actual yes | 0 | 1 | 0 | 1 |
| Actual no | 0 | 4 | 0 | 7 |

**negative_characterization**

| Actual | Model predicted yes | Model predicted no | Baseline predicted yes | Baseline predicted no |
|---|---:|---:|---:|---:|
| Actual yes | 2 | 0 | 0 | 3 |
| Actual no | 0 | 3 | 1 | 4 |

## Development cases (4)

### Model (one recorded run; repeatability not tested)

- Execution mode: frozen hosted_groq artifact (openai/gpt-oss-120b), read from evaluation/, not rerun
- Coverage (validated/total): 4/4
- Exact passes (all four fields): 4/4
- Note: the artifact stores no expected labels or summary; expected labels come from labels-v1.json

| Label | Agreement | Precision | Recall | TP | FP | FN | TN |
|---|---:|---:|---:|---:|---:|---:|---:|
| brand_mentioned | 1.000 | 1.000 | 1.000 | 3 | 0 | 0 | 1 |
| recommended | 1.000 | 1.000 | 1.000 | 1 | 0 | 0 | 3 |
| negative_characterization | 1.000 | 1.000 | 1.000 | 3 | 0 | 0 | 1 |
| observable_position | 1.000 | n/a | n/a | - | - | - | - |

observable_position is graded by exact equality: 4 of 4 cases matched.

### Baseline

- Execution mode: rules baseline (tools/rule_baseline.py), no model
- Coverage (validated/total): 4/4
- Exact passes (all four fields): 1/4

| Label | Agreement | Precision | Recall | TP | FP | FN | TN |
|---|---:|---:|---:|---:|---:|---:|---:|
| brand_mentioned | 1.000 | 1.000 | 1.000 | 3 | 0 | 0 | 1 |
| recommended | 0.750 | n/a | 0.000 | 0 | 0 | 1 | 3 |
| negative_characterization | 0.250 | n/a | 0.000 | 0 | 0 | 3 | 1 |
| observable_position | 1.000 | n/a | n/a | - | - | - | - |

observable_position is graded by exact equality: 4 of 4 cases matched.

## Synthetic edge cases (2)

The model was not run on synthetic cases.

### Baseline

- Execution mode: rules baseline (tools/rule_baseline.py), no model
- Coverage (validated/total): 2/2
- Exact passes (all four fields): 0/2

| Label | Agreement | Precision | Recall | TP | FP | FN | TN |
|---|---:|---:|---:|---:|---:|---:|---:|
| brand_mentioned | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 | 0 |
| recommended | 0.500 | 1.000 | 0.500 | 1 | 0 | 1 | 0 |
| negative_characterization | 0.500 | n/a | 0.000 | 0 | 0 | 1 | 1 |
| observable_position | 0.500 | n/a | n/a | - | - | - | - |

observable_position is graded by exact equality: 1 of 2 cases matched.

## Failed cases

- Held-out: Google AI Mode, prompt 004: Groq rejected the model JSON: it did not match the required schema
- Held-out: ChatGPT, prompt 005: Groq rejected the model JSON: it did not match the required schema
- Held-out: Gemini, prompt 014: Model output broke the contract: negative characterization without a brand mention

## Integrity checks

### Cross-checks

| Check | Result |
|---|---|
| Held-out artifact summary equals recomputed summary | yes |
| Stored passed flags equal recomputation from labels (held-out) | yes |
| Stored passed flags equal recomputation from labels (development) | yes |

The development artifact stores no summary, so only per-case passed flags are compared.

### Score arithmetic

Independent function (absent 0, mentioned 25, recommended 100) versus `visibility_score`.

- Checked: 28 (5 contract-allowed boolean combinations, 14 from expected labels, 9 from validated model results)
- Mismatches: 0

### Report evidence check

**STUB analysis, mechanics only, not model quality**

- Results in the stub analysis: 150
- Problems found in the clean report: 0

| Seeded defect | Flagged |
|---|---|
| evidence id not in analysis | yes |
| failed result in non failure section | yes |
| excerpt not in answer | yes |
| remedy without shared evidence | yes |
| empty quote | yes |

## Limits

- The labels are the project owner's own, not an independent annotation.
- Only four fields are compared: brand_mentioned, recommended, negative_characterization and observable_position. Competitors and excerpt choice are not graded.
- The held-out set is 8 cases and contains one positive recommendation case, so recommended precision and recall rest on very little.
- The model results come from a single frozen run. Repeatability is unverified, so every model-quality statement here is single-run and unverified.
- The baseline cue lists were fixed before the first evaluation run and were not changed afterwards.
- No LLM judges anything here; every comparison is a deterministic rule against the owner's labels.
- Quote traceability (an excerpt occurs verbatim in the answer) is not semantic correctness.
