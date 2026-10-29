from __future__ import annotations

from backend.app.classification import (
    AbsenceRuleClassifier,
    ClassificationOutcome,
    ControlledStubClassifier,
    LiteralAbsenceRouter,
    visibility_score,
)


def test_rule_classifier_marks_absent_brand() -> None:
    outcome = AbsenceRuleClassifier().classify("Other tools are better.", "r1")

    assert outcome.result is not None
    assert outcome.result.brand_mentioned is False
    assert outcome.result.recommended is False
    assert outcome.result.competitors == []
    assert outcome.result.supporting_excerpts == []
    assert outcome.result.uncertainty == "low"
    assert visibility_score(outcome.result) == 0
    assert outcome.execution_mode == "rules"
    assert outcome.model_identifier == "literal-absence-rule-v1"
    assert outcome.attempts[0].validation_error is None


def test_rule_classifier_declines_when_brand_occurs() -> None:
    outcome = AbsenceRuleClassifier().classify("Try KASPARRO today.", "r1")

    assert outcome.result is None
    assert outcome.attempts[0].validation_error == (
        "rule_not_applicable: brand name occurs in the answer"
    )


class RecordingLive(ControlledStubClassifier):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[str] = []

    def classify(self, answer_text: str, response_id: str | None = None) -> ClassificationOutcome:
        self.seen.append(answer_text)
        return super().classify(answer_text, response_id)


def test_router_sends_absent_to_rules_and_mentions_to_live() -> None:
    live = RecordingLive()
    router = LiteralAbsenceRouter(live)

    absent = router.classify("Nothing relevant.", "r1")
    mention = router.classify("Kasparro is good.", "r2")

    assert live.seen == ["Kasparro is good."]
    assert absent.execution_mode == "rules"
    assert mention.execution_mode == "stub"
    assert mention.result is not None and mention.result.brand_mentioned is True
    assert router.execution_mode == "rules+stub"
    assert router.model_identifier == "literal-absence-rule-v1+controlled-stub-v1"
    assert router.prompt_version == live.prompt_version
