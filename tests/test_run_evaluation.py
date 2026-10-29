from __future__ import annotations

import json
from pathlib import Path

from tools.run_evaluation import main

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
    assert markdown.startswith("# ")


def test_report_states_limits_and_seeded_defect_results(tmp_path: Path) -> None:
    data, markdown = run(tmp_path)

    assert "What this does and does not show" in markdown
    assert "No LLM judges anything" in markdown
    assert "STUB analysis, mechanics only, not model quality" in markdown
    checks = data["report_evidence_check"]
    assert checks["clean_problems"] == []
    assert all(checks["seeded_defects_flagged"].values())
    assert len(checks["seeded_defects_flagged"]) == 4


def test_score_arithmetic_has_no_mismatches(tmp_path: Path) -> None:
    data, _ = run(tmp_path)

    assert data["score_arithmetic"]["checked"] > 0
    assert data["score_arithmetic"]["mismatches"] == 0


def test_command_is_deterministic(tmp_path: Path) -> None:
    first, _ = run(tmp_path / "a")
    second, _ = run(tmp_path / "b")

    assert first == second
