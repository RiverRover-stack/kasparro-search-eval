from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_evaluation_split_is_balanced_frozen_and_traceable() -> None:
    labels = json.loads((ROOT / "evaluation" / "labels-v1.json").read_text(encoding="utf-8"))
    responses = {
        row["response_id"]: row
        for row in (
            json.loads(line)
            for line in (ROOT / "data" / "responses.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    cases = labels["supplied_cases"]

    assert Counter(case["engine"] for case in cases) == {"aimode": 4, "chatgpt": 4, "gemini": 4}
    assert Counter(case["split"] for case in cases) == {"development": 4, "held_out": 8}
    assert labels["policy"]["held_out_tuning_allowed"] is False
    assert len(labels["synthetic_cases"]) == 2
    for case in cases:
        source = responses[case["response_id"]]
        assert source["engine"] == case["engine"]
        assert source["prompt_id"] == case["prompt_id"]
        for excerpt in case["expected"]["supporting_excerpts"]:
            assert excerpt in source["answer_text"]


def test_prompt_category_mapping_is_complete_and_freezes_branded_boundary() -> None:
    mapping = json.loads(
        (ROOT / "evaluation" / "prompt-categories-v1.json").read_text(encoding="utf-8")
    )
    covered: dict[int, bool] = {}
    for rule in mapping["rules"]:
        start, end = (int(value) for value in rule["prompt_numbers"].split("-"))
        for number in range(start, end + 1):
            assert number not in covered
            covered[number] = rule["branded"]

    assert sorted(covered) == list(range(1, 51))
    assert all(covered[number] for number in range(1, 31))
    assert not any(covered[number] for number in range(31, 51))
