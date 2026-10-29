from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("reportlab")
pypdf = pytest.importorskip("pypdf")

from tools.make_comparison_pdf import main  # noqa: E402
from tools.run_evaluation import case_name, describe_failed_case  # noqa: E402

EVALUATION = Path(__file__).resolve().parents[1] / "evaluation"


def build(output: Path, *extra: str) -> Path:
    assert main(["--input-dir", str(EVALUATION), "--output", str(output), *extra]) == 0
    return output


def pdf_text(path: Path) -> tuple[int, str]:
    reader = pypdf.PdfReader(str(path))
    return len(reader.pages), "\n".join(page.extract_text() for page in reader.pages)


def test_pdf_has_sections_and_headline_numbers_from_the_json(tmp_path: Path) -> None:
    path = build(tmp_path / "report.pdf")
    pages, text = pdf_text(path)
    summary = json.loads((EVALUATION / "comparison-report.json").read_text(encoding="utf-8"))
    model, baseline = summary["model_held_out"]["summary"], summary["baseline_held_out"]["summary"]
    brand_model = model["per_label"]["brand_mentioned"]["agreement"]
    brand_baseline = baseline["per_label"]["brand_mentioned"]["agreement"]

    assert path.read_bytes().startswith(b"%PDF")
    assert 4 <= pages <= 10
    for word in ("Confusion", "Precision", "Recall", "Agreement", "At a glance", "Failed cases", "Integrity checks", "Limits"):
        assert word in text
    assert f"{model['validated_cases']}/{model['total_cases']}" in text
    assert f"{model['passed_cases']} vs {baseline['passed_cases']}" in text
    assert f"{brand_model:.3f} vs {brand_baseline:.3f}" in text
    assert f"Page {pages} of {pages}" in text
    assert "Google AI Mode, prompt 004" in text
    assert "28 checks" in text and "0 mismatches" in text
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", text)
    assert not re.search(r"\b(True|False|None)\b", text)


def test_pdf_is_byte_stable_and_previews_are_written_only_on_request(tmp_path: Path) -> None:
    first = build(tmp_path / "a.pdf", "--preview-dir", str(tmp_path / "previews"))
    second = build(tmp_path / "b.pdf")

    assert first.read_bytes() == second.read_bytes()
    assert len(list((tmp_path / "previews").glob("*.png"))) == 3
    assert not list(tmp_path.glob("*.png"))


def test_failed_cases_are_described_by_engine_and_prompt_number() -> None:
    labels = json.loads((EVALUATION / "labels-v1.json").read_text(encoding="utf-8"))
    response_id = next(
        case["response_id"]
        for case in labels["supplied_cases"]
        if case["engine"] == "aimode" and case["prompt_id"].endswith(":004")
    )

    assert case_name(response_id, labels) == "Google AI Mode, prompt 004"
    assert describe_failed_case({"response_id": response_id, "last_attempt_error": ""}, labels).startswith("Google AI Mode, prompt 004: ")
