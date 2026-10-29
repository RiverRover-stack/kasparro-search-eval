from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CLASSIFICATION_CONTRACT_VERSION = "classification-v1"


class EvidenceKind(StrEnum):
    MENTION = "mention"
    RECOMMENDATION = "recommendation"
    NEGATIVE = "negative_characterization"
    POSITION = "position"
    COMPETITOR = "competitor"


class SupportingExcerpt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind
    quote: str = Field(min_length=1, max_length=1000)


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["classification-v1"]
    brand_mentioned: bool
    recommended: bool
    negative_characterization: bool
    competitors: list[str] = Field(default_factory=list, max_length=30)
    observable_position: int | None = Field(default=None, ge=1)
    supporting_excerpts: list[SupportingExcerpt] = Field(default_factory=list, max_length=12)
    uncertainty: Literal["low", "medium", "high"]
    uncertainty_reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_semantics(self) -> "ClassificationResult":
        if self.recommended and not self.brand_mentioned:
            raise ValueError("A recommendation requires a brand mention")
        if self.negative_characterization and not self.brand_mentioned:
            raise ValueError("Negative characterization requires a brand mention")
        if not self.brand_mentioned and self.observable_position is not None:
            raise ValueError("An absent brand cannot have an observable position")
        return self

    def verify_excerpts(self, answer_text: str) -> None:
        literal_brand_present = "kasparro" in answer_text.casefold()
        if self.brand_mentioned != literal_brand_present:
            raise ValueError(
                "brand_mentioned must agree with literal Kasparro presence in the archived answer"
            )
        fabricated = [item.quote for item in self.supporting_excerpts if item.quote not in answer_text]
        if fabricated:
            raise ValueError(f"Supporting excerpt not found in archived answer: {fabricated[0]!r}")
        excerpt_kinds = {item.kind for item in self.supporting_excerpts}
        if self.brand_mentioned and not any(
            "kasparro" in item.quote.casefold() for item in self.supporting_excerpts
        ):
            raise ValueError("A brand mention requires a Kasparro-containing supporting excerpt")
        required_evidence = (
            (self.recommended, EvidenceKind.RECOMMENDATION, "recommendation"),
            (self.negative_characterization, EvidenceKind.NEGATIVE, "negative characterization"),
            (self.observable_position is not None, EvidenceKind.POSITION, "observable position"),
        )
        for active, kind, label in required_evidence:
            if active and kind not in excerpt_kinds:
                raise ValueError(f"{label} requires a matching supporting excerpt")
            if not active and kind in excerpt_kinds:
                raise ValueError(f"{label} excerpt contradicts the false/null classification field")


def visibility_score(result: ClassificationResult) -> int:
    """Score visibility and endorsement only; do not infer accuracy or business impact."""
    if result.recommended:
        return 100
    if result.brand_mentioned:
        return 25
    return 0


def normalize_inactive_evidence(
    result: ClassificationResult,
) -> tuple[ClassificationResult, int]:
    """Drop only excerpts that contradict an inactive semantic field; retain raw output separately."""
    allowed = {EvidenceKind.MENTION}
    if result.recommended:
        allowed.add(EvidenceKind.RECOMMENDATION)
    if result.negative_characterization:
        allowed.add(EvidenceKind.NEGATIVE)
    if result.observable_position is not None:
        allowed.add(EvidenceKind.POSITION)
    if result.competitors:
        allowed.add(EvidenceKind.COMPETITOR)
    retained = [item for item in result.supporting_excerpts if item.kind in allowed]
    dropped = len(result.supporting_excerpts) - len(retained)
    if not result.brand_mentioned:
        dropped = len(result.supporting_excerpts)
        retained = []
    return result.model_copy(update={"supporting_excerpts": retained}), dropped
