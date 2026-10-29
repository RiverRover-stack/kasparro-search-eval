from __future__ import annotations

import pytest

from backend.app.classification import ClassificationResult


def result(**overrides) -> ClassificationResult:
    values = {
        "contract_version": "classification-v1",
        "brand_mentioned": False,
        "recommended": False,
        "negative_characterization": False,
        "competitors": [],
        "observable_position": None,
        "supporting_excerpts": [],
        "uncertainty": "low",
        "uncertainty_reason": "The answer is explicit.",
    }
    values.update(overrides)
    return ClassificationResult.model_validate(values)


# regression for the 28 Oct 2026 gemma3 failure (journey/dev-notes.md)
def test_regression_quote_with_stripped_markdown_is_rejected() -> None:
    classification = result(
        brand_mentioned=True,
        supporting_excerpts=[{"kind": "mention", "quote": "Kasparro is useful."}],
    )

    with pytest.raises(ValueError, match="not found"):
        classification.verify_excerpts("**Kasparro** is useful.")


# regression for the 28 Oct 2026 gemma3 failure (journey/dev-notes.md)
def test_regression_missing_brand_flag_is_rejected_when_text_has_brand() -> None:
    with pytest.raises(ValueError, match="literal Kasparro presence"):
        result(brand_mentioned=False).verify_excerpts("Kasparro appears here.")
