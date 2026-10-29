from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable

SAMPLE_RULE_VERSION = "live-sample-v1"


def select_live_sample(responses: Iterable, excluded_ids: set[str], per_engine: int = 13) -> list[str]:
    """Pick the first `per_engine` brand-mention answers per engine, ordered by id hash."""
    by_engine: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for response in responses:
        if "kasparro" in response.answer_text.casefold() and response.id not in excluded_ids:
            digest = hashlib.sha256(response.id.encode()).hexdigest()
            by_engine[response.engine].append((digest, response.id))
    return [
        response_id
        for engine in sorted(by_engine)
        for _, response_id in sorted(by_engine[engine])[:per_engine]
    ]
