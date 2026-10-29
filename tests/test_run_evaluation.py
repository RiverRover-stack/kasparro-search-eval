from __future__ import annotations

import json
import re
from pathlib import Path

from tools.run_evaluation import case_name, describe_failed_case, failure_reason, main

ROOT = Path(__file__).resolve().parents[1]


def run(output_dir: Path) -> tuple[dict, str]:
    assert main(["--output-dir", str(output_dir)]) == 0
    data = json.loads((output_dir / "comparison-report.json").read_text(encoding="utf-8"))
    return data, (output_dir / "comparison-report.md").read_text(encoding="utf-8")


def test_outputs_are_written_and_model_summary_matches_artifact(tmp_path: Path) -> None:
    data, markdown = run(tmp_path)
    artifact = json.loads((ROOT / "evaluation" / "groq-held-out-120b.json").read_text(encoding="utf-8"))

    assert data["model_held_out"]["summary"] == artifact["summary"]
    assert data["model_held_out"]["summary_matches_artifact"] is True
    assert data["baseline_held_out"]["summary"]["total_cases"] == 8
    assert data["model_development"]["summary"]["total_cases"] == 4
    assert data["baseline_synthetic"]["summary"]["total_cases"] == 2
    assert markdown.startswith("# Kasparro AI visibility classifier: model versus keyword baseline")
    for heading in (
        "## Headline results",
        "## How to read the metrics",
        "## Held-out final check",
        "## Development cases",
        "## Synthetic edge cases",
        "### Confusion matrices",
        "## Failed cases",
        "## Integrity checks",
        "## Limits",
    ):
        assert heading in markdown
    assert "| Label | Agreement | Precision | Recall | TP | FP | FN | TN |" in markdown
    assert "| Model (one recorded run; repeatability not tested) | 5/8 | 62.5% | 4/8 |" in markdown


def test_report_states_limits_and_seeded_defect_results(tmp_path: Path) -> None:
    data, markdown = run(tmp_path)

    assert "## Limits" in markdown
    assert "No LLM judges anything" in markdown
    assert "STUB analysis, mechanics only, not model quality" in markdown
    checks = data["report_evidence_check"]
    assert checks["clean_problems"] == []
    assert all(checks["seeded_defects_flagged"].values())
    assert len(checks["seeded_defects_flagged"]) == 5
    assert "empty_quote" in checks["seeded_defects_flagged"]
    assert "| empty quote | yes |" in markdown
    assert "True" not in markdown and "False" not in markdown


def test_score_arithmetic_has_no_mismatches(tmp_path: Path) -> None:
    data, _ = run(tmp_path)

    assert data["score_arithmetic"]["checked"] > 0
    assert data["score_arithmetic"]["mismatches"] == 0


def test_command_is_deterministic(tmp_path: Path) -> None:
    first, _ = run(tmp_path / "a")
    second, _ = run(tmp_path / "b")

    assert first == second


def test_markdown_has_no_hashes_and_names_failed_cases_by_engine_and_prompt(tmp_path: Path) -> None:
    data, markdown = run(tmp_path)

    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", markdown)
    assert not re.search(r"[0-9a-f]{40}|[0-9a-f]{64}", markdown)
    assert len(data["model_held_out"]["failed_cases"]) == 3
    assert "- Held-out: Google AI Mode, prompt 004: Groq rejected the model JSON" in markdown
    assert "- Held-out: ChatGPT, prompt 005: " in markdown
    assert "- Held-out: Gemini, prompt 014: Model output broke the contract" in markdown


def test_failed_case_description_uses_engine_and_prompt_number() -> None:
    labels = json.loads((ROOT / "evaluation" / "labels-v1.json").read_text(encoding="utf-8"))
    aimode_004 = next(
        case["response_id"]
        for case in labels["supplied_cases"]
        if case["engine"] == "aimode" and case["prompt_id"].endswith(":004")
    )

    assert case_name(aimode_004, labels) == "Google AI Mode, prompt 004"
    assert case_name("not-a-known-id", labels) == "Unknown case"
    assert describe_failed_case({"response_id": aimode_004, "last_attempt_error": "boom"}, labels) == (
        "Google AI Mode, prompt 004: Model call failed"
    )
    assert "required schema" in failure_reason("Groq HTTP 400: Generated JSON does not match the expected schema.")
    assert "without a brand mention" in failure_reason("Negative characterization requires a brand mention")
