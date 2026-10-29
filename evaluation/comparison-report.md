# Baseline versus frozen Groq comparison

## What this does and does not show

- The labels are the project owner's own, not an independent annotation.
- Only four fields are compared: brand_mentioned, recommended, negative_characterization and observable_position. Competitors and excerpt choice are not graded.
- The held-out set is 8 cases and contains one positive recommendation case, so recommended precision and recall rest on very little.
- The model results come from a single frozen run. Repeatability is unverified, so every model-quality statement here is single-run and unverified.
- The baseline cue lists were fixed before the first evaluation run and were not changed afterwards.
- No LLM judges anything here; every comparison is a deterministic rule against the owner's labels.
- Quote traceability (an excerpt occurs verbatim in the answer) is not semantic correctness.

- Baseline: rules baseline (tools/rule_baseline.py), no model.
- Model: frozen hosted_groq artifact (openai/gpt-oss-120b), read from evaluation/, not rerun. The model was not run on the synthetic cases.

## Held-out cases (8)

### Model (single run, unverified)

- Execution mode: frozen hosted_groq artifact (openai/gpt-oss-120b), read from evaluation/, not rerun
- Coverage (validated/total): 5/8
- Exact passes (all four fields): 4/8

| Label | Agreement | Precision | Recall | Counts |
|---|---:|---:|---:|---|
| brand_mentioned | 0.625 | 1.000 | 1.000 | tp 3 fp 0 fn 0 tn 2 |
| recommended | 0.500 | n/a | 0.000 | tp 0 fp 0 fn 1 tn 4 |
| negative_characterization | 0.625 | 1.000 | 1.000 | tp 2 fp 0 fn 0 tn 3 |
| observable_position | 0.625 | n/a | n/a | matches 5/8 |

- Failed case `67b714d5-bf90-42c2-a360-1d1d3149c1f8`: Groq HTTP 400: Generated JSON does not match the expected schema. Please adjust your prompt. See 'failed_generation' for more details. Error: jsonschema: '/supp

- Failed case `08f81acc-0824-4e3a-a5d5-58446e2a6a90`: Groq HTTP 400: Generated JSON does not match the expected schema. Please adjust your prompt. See 'failed_generation' for more details. Error: jsonschema: '/supp

- Failed case `5beb2a32-6c6c-42d8-861c-9fc9680b9930`: ValidationError: 1 validation error for ClassificationResult Value error, Negative characterization requires a brand mention [type=value_error, input_value={'co

### Baseline

- Execution mode: rules baseline (tools/rule_baseline.py), no model
- Coverage (validated/total): 8/8
- Exact passes (all four fields): 4/8

| Label | Agreement | Precision | Recall | Counts |
|---|---:|---:|---:|---|
| brand_mentioned | 1.000 | 1.000 | 1.000 | tp 5 fp 0 fn 0 tn 3 |
| recommended | 0.875 | n/a | 0.000 | tp 0 fp 0 fn 1 tn 7 |
| negative_characterization | 0.500 | 0.000 | 0.000 | tp 0 fp 1 fn 3 tn 4 |
| observable_position | 1.000 | n/a | n/a | matches 8/8 |

## Development cases (4)

### Model (single run, unverified)

- Execution mode: frozen hosted_groq artifact (openai/gpt-oss-120b), read from evaluation/, not rerun
- Coverage (validated/total): 4/4
- Exact passes (all four fields): 4/4
- Note: the artifact stores no expected labels or summary; expected labels come from labels-v1.json

| Label | Agreement | Precision | Recall | Counts |
|---|---:|---:|---:|---|
| brand_mentioned | 1.000 | 1.000 | 1.000 | tp 3 fp 0 fn 0 tn 1 |
| recommended | 1.000 | 1.000 | 1.000 | tp 1 fp 0 fn 0 tn 3 |
| negative_characterization | 1.000 | 1.000 | 1.000 | tp 3 fp 0 fn 0 tn 1 |
| observable_position | 1.000 | n/a | n/a | matches 4/4 |

### Baseline

- Execution mode: rules baseline (tools/rule_baseline.py), no model
- Coverage (validated/total): 4/4
- Exact passes (all four fields): 1/4

| Label | Agreement | Precision | Recall | Counts |
|---|---:|---:|---:|---|
| brand_mentioned | 1.000 | 1.000 | 1.000 | tp 3 fp 0 fn 0 tn 1 |
| recommended | 0.750 | n/a | 0.000 | tp 0 fp 0 fn 1 tn 3 |
| negative_characterization | 0.250 | n/a | 0.000 | tp 0 fp 0 fn 3 tn 1 |
| observable_position | 1.000 | n/a | n/a | matches 4/4 |

## Synthetic cases (2)

The model was not run on synthetic cases.

### Baseline

- Execution mode: rules baseline (tools/rule_baseline.py), no model
- Coverage (validated/total): 2/2
- Exact passes (all four fields): 0/2

| Label | Agreement | Precision | Recall | Counts |
|---|---:|---:|---:|---|
| brand_mentioned | 1.000 | 1.000 | 1.000 | tp 2 fp 0 fn 0 tn 0 |
| recommended | 0.500 | 1.000 | 0.500 | tp 1 fp 0 fn 1 tn 0 |
| negative_characterization | 0.500 | n/a | 0.000 | tp 0 fp 0 fn 1 tn 1 |
| observable_position | 0.500 | n/a | n/a | matches 1/2 |

## Cross-checks

- Held-out artifact summary equals recomputed summary: True
- Development artifact stores no summary, so only per-case passed flags are compared.
- Stored passed flags equal recomputation from labels (held-out): True
- Stored passed flags equal recomputation from labels (development): True

## Score arithmetic

Independent function (absent 0, mentioned 25, recommended 100) versus `visibility_score`.

- Checked: 28 (5 contract-allowed boolean combinations, 14 from expected labels, 9 from validated model results)
- Mismatches: 0

## Report evidence check

**STUB analysis, mechanics only, not model quality**

- Results in the stub analysis: 150
- Problems found in the clean report: 0
- Seeded defect `evidence_id_not_in_analysis` flagged: True
- Seeded defect `failed_result_in_non_failure_section` flagged: True
- Seeded defect `excerpt_not_in_answer` flagged: True
- Seeded defect `remedy_without_shared_evidence` flagged: True
