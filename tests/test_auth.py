from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.auth import require_analyst, require_reviewer
from backend.app.main import app


def _route_calls(path: str, method: str) -> set:
    route = next(
        item for item in app.routes if getattr(item, "path", None) == path and method in item.methods
    )
    calls, pending = set(), [route.dependant]
    while pending:
        dependant = pending.pop()
        calls.add(dependant.call)
        pending.extend(dependant.dependencies)
    return calls


@pytest.mark.parametrize(("path", "method"), [("/datasets", "POST"), ("/analyses", "POST")])
def test_import_and_analysis_require_the_analyst_role(path: str, method: str) -> None:
    assert require_analyst in _route_calls(path, method)


def test_analyst_check_denies_the_reviewer_role() -> None:
    with pytest.raises(HTTPException) as denied:
        require_analyst("reviewer")
    assert denied.value.status_code == 403
    assert require_analyst("analyst") == "analyst"


def test_decision_route_stays_reviewer_only() -> None:
    assert require_reviewer in _route_calls("/reports/{report_id}/decision", "POST")
