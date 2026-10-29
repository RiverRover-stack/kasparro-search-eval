# ADR 0006: Findings generator and separate number blocks

Status: proposed, awaiting owner review (29 October 2026). The diagnostic rule was approved by the owner the same day; the rest of this record is not yet approved.

## Context

The first report writer produced generic wording about the pipeline and linked the first three
responses as evidence. It did not say where Kasparro wins or loses. The live run (150 answers: 105
successful, 12 failed, 33 skipped) also showed that the blended average mixes two different things:
78 absences found by a literal rule over every answer, and model results on only 27 of the 72 answers
that name Kasparro. That average is not a measure of Kasparro's visibility.

## Decision

- Add `backend/app/findings.py`: pure functions that build the report content from stored results.
  `_initial_content` in `reports.py` calls it. Routes stay thin.
- The report summary has two separate blocks, each with valid, failed and skipped beside every number:
  - **Literal block, all 150 answers:** how often the name "Kasparro" appears, by engine and by
    branded/unbranded prompt (`prompt-categories-v1`).
  - **Model block, answers classified by the hosted model only:** mentioned-only, recommended and
    negative counts, and how many model calls failed. It states that very few recommendations may mean
    the model under-detects them.
- A result counts as model-classified if its response has no `model_attempts` row with
  `execution_mode == "rules"`. The text of `uncertainty_reason` is not used, because it is easy to break.
- The three diagnostics are one per kind of finding, computed from the counts, never hardcoded:
  1. Unbranded prompts: the name rate over all engines together, with the per-engine split in the text.
  2. Branded prompts: the engine whose name rate is furthest from the branded average; ties broken by
     engine order (chatgpt, gemini, aimode).
  3. Model block: what the model found on its valid answers (mentioned-only, recommended, negative,
     failed calls), with the note that few recommendations may mean under-detection. Its evidence IDs
     are model-classified answers only.
  Same data gives the same report. Each diagnostic keeps three things apart: recorded pattern,
  possible explanation (a hypothesis), and the evidence that would test it, with valid, failed and
  skipped coverage beside the numbers.
- Remedies get an optional `problem` field on `ReportRemedy`. It is optional so report versions saved
  before this change still load and keep their content hashes. Every newly generated remedy fills it in.
- No finding cites the blended average, and a newly generated report summary does not contain it: the
  old `aggregate`, `by_engine`, `by_prompt_branding` and `shared_prompt_comparison` keys are no longer
  written. The analysis itself (`GET /analyses/{id}`) still stores and returns them. Old report versions
  are not rewritten, still load and keep their content hashes. The summary keeps these metadata keys:
  `execution_mode`, `model_identifier`, `prompt_version`, `prompt_mapping_version`, `score_scope`.
- Empty groups: if there are no branded or no unbranded prompts, or no model-classified answers,
  report creation fails with the new `409 analysis_not_reportable` (added in this change). A plain stub
  analysis still gives valid model results, so stub mode does not trigger it. No
  fallback text is invented. If every unbranded answer names the brand, the first diagnostic cites
  any unbranded answers.

## Alternatives considered

- Name the three diagnostics by hand: more control, but it depends on the author and cannot be rerun.
- Add explicit fields for each part of a diagnostic: the existing fields already match the three parts,
  so this would only change the API.
- Detect rule-classified results from the explanation text: simpler, but breaks if the wording changes.

## Consequences

- On the live run the diagnostics are: unbranded 0 of 60 named (20 per engine); branded, Gemini 22 of 30
  against 25 of 30 for ChatGPT and AI Mode; model 27 valid, 12 of 39 calls failed, 26 mentioned-only,
  1 recommended, 11 negative. An earlier "largest gap from the overall name rate" rule gave three
  near-identical unbranded findings, so it was replaced.
- Only the branded-prompt average is named in the text. The overall blended average is not.
- `tools/check_report_evidence.py` requires every remedy to share a response ID with a diagnostic, so a
  remedy whose own evidence has no overlap also cites the first diagnostic's evidence ID. The owner
  accepted that this ID may be a little off-topic.
- The held-out sentence is fixed text taken from `evaluation/groq-held-out-120b.md`: only 5 of 8 cases
  gave a valid answer, and the model found 0 recommendations among them. It is shown only for hosted
  runs.
- Titles and wording that depend on a count (unbranded named 0 or more, failures 0 or more, quote
  rejections 0 or more) are chosen from the numbers, so they stay true on other data.
- Evidence excerpts: D1 and D2 cite answers settled by the literal rule or never sent, so they have
  no stored model excerpts. They now carry verbatim excerpts from the archived answer, written into
  `evidence_needed` as `Response <id>: "<quote>"` (no schema change). D1 quotes the opening sentence of
  each cited unbranded answer; this shows what the engine said instead and proves absence only weakly
  (the literal count over the whole answer proves absence). D2 quotes the sentence that names
  Kasparro, or, if the cited answer does not name it, the opening sentence, labelled as such. Quotes
  are at most about 300 characters; a longer sentence gives a verbatim prefix with the truncation
  marked outside the quote. `tools/check_report_evidence.py` checks that every quoted excerpt is an
  exact substring of the cited answer. This proves the words are real, not what they mean. D3 still
  uses the stored model excerpts.
- The sentence-number remedy for the quote failures is a proposal. It has not been tested.
- Existing report versions are not rewritten. Only new drafts use the new content.
