# Decision note

Numbers below come from the files in `evaluation/`, and `evaluation/analysis-output.json`
(made from the one live run). Nothing here is a claim about how good the model is in general.

## Scoring and aggregation

Each answer scores 0 (Kasparro absent), 25 (mentioned) or 100 (recommended). The rule is fixed
arithmetic with no model in it. Other facts (negative wording, position, citations) stay as separate
fields.

The report shows two number blocks and never joins them:

- **Name counts, all 150 answers.** A plain text match for "Kasparro": ChatGPT 25 of 50, Google AI Mode
  25 of 50, Gemini 22 of 50. This is exact, whatever the model did.
- **Model results, only the answers the model read.** 27 valid, 12 failed, out of 39 sent. In the 27:
  26 mentioned only, 1 recommended, 11 negative (this overlaps the others).

Every number sits next to its coverage (valid, failed, skipped). The single average (about 7.1) is
misleading: it covers 105 scored answers, and 78 of them are zeros set by the text rule. The 45 mention
answers that failed or were skipped are not in it. It mixes two different kinds of evidence, so the
report does not show it.

## Review design

Every edit makes a new version. Submitting freezes a version. A decision (with a required comment) binds to
that one version. Only an approved version can be exported, and editing after approval makes a new draft
that needs its own approval. Roles come from two secret tokens in the server environment, so a request
cannot claim a role. Audit events hold no secrets.

## Alternatives considered

- A small local model (`gemma3:4b`) failed the development checks, so Groq `gpt-oss-120b` was used.
- One blended score: rejected for the reason above.
- Writing the three findings by hand: rejected, because they could not be re-run on new data.
- An identity provider instead of environment tokens: left for later. Tokens are enough for a local review.

## Top remedy (a proposal, not tested)

11 of the 12 failed model calls failed because the quoted text did not match the answer exactly. Proposal:
the model returns sentence numbers, and the code copies the exact sentence. This might recover the
failed answers. It has not been tried. Any change to the reply format or the model voids the frozen
evaluation, so it would need a new freeze and new test cases. It must not be tuned on the 8 held-out cases.

## The failure and the fix

12 of 39 model calls failed: 11 quote rejections and 1 contract error. Two fixes are in place. The 78
answers that never contain the name are settled by a literal rule, without the model. A failed call is
recorded as failed, never as brand absence. The 33 answers not sent (free plan limit) are marked skipped
with a reason.

## Biggest risks

1. The model may under-detect recommendations: 1 recommended in 27. On the 8 held-out cases only 5 gave a
   valid answer, and recall for recommendations was 0 on the one positive case. The simple keyword rule
   also scored 0 there. Eight cases is very small, and the labels are the owner's own.
2. The second finding is misleading on the live run. Prompts 026 to 030 are labelled "branded" but do not
   name Kasparro, so Gemini's 22 of 30 is really 22 of 25, and two of the three answers cited do not show
   the gap. Fixed in the report: the second finding now cites only answers to prompts that name Kasparro and says
   that 5 of 30 branded-labelled prompts do not. The frozen mapping is unchanged. The saved output file
   was made again and lists only what remains.

## Left out, and why

No dashboard, Docker, deployment, crawling, vector search, extra agents, resuming a stopped analysis,
protection against two reviewers at once, or approval expiry. They are not needed to show the workflow.
Unique-link counting is not built either. The model was not run on all 150 answers.

## Questions to answer before release

- Keep the frozen prompt labels and change finding 2, or approve a new mapping?
- Does a person reading the 27 valid answers find more recommendations than the model did?
- Is a new freeze with sentence numbers worth the cost?
- What were the real active hours? **Owner to supply; not filled in here.**

## AI assistance

An AI coding assistant (Claude Code) wrote and reviewed much of the code and the documents. The owner
reviewed the decisions and approves each commit. The model's output is input for human review, not fact.
