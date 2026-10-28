from __future__ import annotations

import pytest

from tools.benchmark_held_out import build_summary
from tools.freeze_hosted_evaluation import validate_development_result


def development_document(model: str = "openai/gpt-oss-120b") -> dict[str, object]:
    return {
        "split": "development",
        "provider": "groq",
        "all_passed": True,
        "cases": [
            {
                "model_identifier": model,
                "validated": True,
                "passed": True,
                "label_agreement": {
                    "brand_mentioned": True,
                    "recommended": True,
                    "negative_characterization": True,
                    "observable_position": True,
                },
            }
            for _ in range(4)
        ],
    }


def test_development_freeze_gate_accepts_four_passing_cases() -> None:
    validate_development_result(development_document(), "openai/gpt-oss-120b")


def test_development_freeze_gate_rejects_model_drift() -> None:
    with pytest.raises(ValueError, match="configured frozen model"):
        validate_development_result(
            development_document("openai/gpt-oss-20b"),
            "openai/gpt-oss-120b",
        )


def test_held_out_summary_reports_coverage_and_label_errors() -> None:
    records = [
        {
            "validated": True,
            "passed": True,
            "expected": {
                "brand_mentioned": True,
                "recommended": False,
                "negative_characterization": False,
                "observable_position": None,
            },
            "result": {
                "brand_mentioned": True,
                "recommended": False,
                "negative_characterization": False,
                "observable_position": None,
            },
        },
        {
            "validated": True,
            "passed": False,
            "expected": {
                "brand_mentioned": False,
                "recommended": False,
                "negative_characterization": True,
                "observable_position": 1,
            },
            "result": {
                "brand_mentioned": True,
                "recommended": False,
                "negative_characterization": False,
                "observable_position": None,
            },
        },
    ]

    summary = build_summary(records)

    assert summary["validated_cases"] == 2
    assert summary["passed_cases"] == 1
    assert summary["per_label"]["brand_mentioned"] == {
        "tp": 1,
        "tn": 0,
        "fp": 1,
        "fn": 0,
        "precision": 0.5,
        "recall": 1.0,
        "agreement": 0.5,
    }
    assert summary["per_label"]["observable_position"]["agreement"] == 0.5
