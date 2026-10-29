"""Independent checks that a report's evidence links resolve to real, faithful results."""
from __future__ import annotations

FAILURE_SECTIONS = ("coverage", "review-failures")


def check_report_evidence(content, results_by_response, answers_by_response) -> list[str]:
    data = content if isinstance(content, dict) else content.model_dump()
    sections = [(item["id"], item) for item in data["diagnostics"] + data["remedies"]]
    problems: list[str] = []
    for section_id, item in sections:
        for response_id in item["evidence_response_ids"]:
            result = results_by_response.get(response_id)
            if result is None:
                problems.append(f"{section_id}: evidence {response_id} is not in the analysis")
                continue
            if section_id not in FAILURE_SECTIONS and result["status"] != "successful":
                problems.append(
                    f"{section_id}: evidence {response_id} has status {result['status']}, not successful"
                )
            answer = answers_by_response.get(response_id, "")
            classification = result["classification"] or {}
            for excerpt in classification.get("supporting_excerpts", []):
                if excerpt["quote"] not in answer:
                    problems.append(
                        f"{section_id}: excerpt for {response_id} not found in answer: {excerpt['quote'][:60]!r}"
                    )
    diagnostic_ids = {
        response_id for item in data["diagnostics"] for response_id in item["evidence_response_ids"]
    }
    for remedy in data["remedies"]:
        if not diagnostic_ids & set(remedy["evidence_response_ids"]):
            problems.append(f"{remedy['id']}: remedy shares no evidence with any diagnostic")
    return problems
