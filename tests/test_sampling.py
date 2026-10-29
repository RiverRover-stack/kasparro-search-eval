from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.importer import import_pack
from backend.app.models import ResponseRecord
from backend.app.sampling import SAMPLE_RULE_VERSION, select_live_sample

ROOT = Path(__file__).resolve().parents[1]


class Row:
    def __init__(self, id: str, engine: str, answer_text: str) -> None:
        self.id, self.engine, self.answer_text = id, engine, answer_text


def synthetic_rows() -> list[Row]:
    rows = [Row(f"a{i}", "chatgpt", "Kasparro is listed.") for i in range(30)]
    rows += [Row(f"b{i}", "gemini", "kasparro appears.") for i in range(20)]
    rows += [Row("none", "gemini", "No brand here.")]
    return rows


def test_sample_is_deterministic_and_bounded_per_engine() -> None:
    first = select_live_sample(synthetic_rows(), set())
    second = select_live_sample(list(reversed(synthetic_rows())), set())

    assert first == second
    assert sum(i.startswith("a") for i in first) == 13
    assert sum(i.startswith("b") for i in first) == 13
    assert "none" not in first
    assert SAMPLE_RULE_VERSION == "live-sample-v1"


def test_sample_excludes_given_ids() -> None:
    base = select_live_sample(synthetic_rows(), set())
    excluded = {base[0]}
    assert base[0] not in select_live_sample(synthetic_rows(), excluded)


def test_real_pack_sample_is_39_mention_answers_outside_labels(
    session_factory: sessionmaker[Session],
) -> None:
    labels = json.loads((ROOT / "evaluation" / "labels-v1.json").read_text(encoding="utf-8"))
    labelled = {case["response_id"] for case in labels["supplied_cases"]}
    with session_factory() as session:
        import_pack(session, ROOT)
        responses = list(session.scalars(select(ResponseRecord)))
        sample = select_live_sample(responses, labelled)
        by_id = {r.id: r for r in responses}

    assert labelled <= set(by_id)
    assert len(sample) == 39 and len(set(sample)) == 39
    assert not set(sample) & labelled
    assert all("kasparro" in by_id[i].answer_text.casefold() for i in sample)
