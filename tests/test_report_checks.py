from __future__ import annotations

from copy import deepcopy

from backend.app.schemas import ReportContent
from tools.check_report_evidence import check_report_evidence

ANSWERS = {
    "r1": "Kasparro is a visibility tool. Acme is another.",
    "r2": "Nothing about the brand here.",
}
RESULTS = {
    "r1": {
        "status": "successful",
        "classification": {"supporting_excerpts": [{"kind": "mention", "quote": "Kasparro is a visibility tool."}]},
    },
    "r2": {"status": "failed", "classification": None},
}


def make_content() -> dict:
    def diagnostic(section_id: str, ids: list[str]) -> dict:
        return {
            "id": section_id,
            "title": "t",
            "observed_pattern": "o",
            "possible_explanation": "p",
            "evidence_needed": "e",
            "uncertainty": "low",
            "evidence_response_ids": ids,
        }

    def remedy(section_id: str, priority: int, ids: list[str]) -> dict:
        return {
            "id": section_id,
            "priority": priority,
            "title": "t",
            "evidence_response_ids": ids,
            "action": "a",
            "expected_benefit": "b",
            "effort": "low",
            "uncertainty": "low",
            "validation_step": "v",
        }

    return {
        "analysis_id": "a",
        "summary": {},
        "diagnostics": [
            diagnostic("coverage", ["r1", "r2"]),
            diagnostic("visibility", ["r1"]),
            diagnostic("engine-comparison", ["r1"]),
        ],
        "remedies": [
            remedy("review-failures", 1, ["r2"]),
            remedy("verify-evidence", 2, ["r1"]),
            remedy("repeat-sampling", 3, ["r1"]),
        ],
    }


def problems(content: dict, results=RESULTS, answers=ANSWERS) -> list[str]:
    return check_report_evidence(ReportContent.model_validate(content), results, answers)


def test_clean_report_has_no_problems() -> None:
    assert problems(make_content()) == []


def test_dict_content_is_accepted() -> None:
    assert check_report_evidence(make_content(), RESULTS, ANSWERS) == []


def test_unknown_evidence_id_is_flagged() -> None:
    content = make_content()
    content["diagnostics"][1]["evidence_response_ids"] = ["missing"]

    assert any("missing" in item and "not in the analysis" in item for item in problems(content))


def test_failed_result_in_non_failure_section_is_flagged() -> None:
    content = make_content()
    content["diagnostics"][1]["evidence_response_ids"] = ["r2"]

    found = problems(content)
    assert any("visibility" in item and "r2" in item and "failed" in item for item in found)


def test_failed_result_in_failure_sections_is_allowed() -> None:
    assert problems(make_content()) == []


def test_excerpt_not_in_answer_is_flagged() -> None:
    results = deepcopy(RESULTS)
    results["r1"]["classification"]["supporting_excerpts"][0]["quote"] = "Kasparro is **a** tool."

    assert any("not found in answer" in item for item in problems(make_content(), results))


def test_remedy_without_shared_evidence_is_flagged() -> None:
    content = make_content()
    content["diagnostics"][0]["evidence_response_ids"] = ["r2"]
    content["diagnostics"][1]["evidence_response_ids"] = ["r2"]
    content["diagnostics"][2]["evidence_response_ids"] = ["r2"]

    found = problems(content)
    assert any("verify-evidence" in item and "shares no evidence" in item for item in found)


def test_empty_quoted_excerpt_is_flagged() -> None:
    content = make_content()
    content["diagnostics"][1]["evidence_needed"] = 'Response r1: ""'

    found = problems(content)
    assert any("visibility" in item and "r1" in item and "empty" in item for item in found)


def test_non_empty_quoted_excerpt_still_passes() -> None:
    content = make_content()
    content["diagnostics"][1]["evidence_needed"] = 'Response r1: "Kasparro is a visibility tool." (start of the sentence)'

    assert problems(content) == []
