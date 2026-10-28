# Frozen Groq held-out evaluation

- Model: `openai/gpt-oss-120b`
- Prompt: `visibility-classifier-v6`
- Validated coverage: 5/8
- Exact case passes: 4/8

| Label | Agreement | Precision | Recall |
|---|---:|---:|---:|
| brand_mentioned | 0.625 | 1.000 | 1.000 |
| recommended | 0.500 | n/a | 0.000 |
| negative_characterization | 0.625 | 1.000 | 1.000 |
| observable_position | 0.625 | n/a | n/a |

Held-out failures must be recorded as limitations and must not be used to tune this frozen prompt.
Exact-source validation establishes traceability, not semantic correctness of an excerpt.
