from __future__ import annotations

import hmac
from typing import Literal

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings


Role = Literal["analyst", "reviewer"]
bearer = HTTPBearer(auto_error=False)


def _configured_tokens() -> dict[Role, str]:
    settings = Settings.from_environment()
    tokens: dict[Role, str] = {}
    if settings.analyst_token:
        tokens["analyst"] = settings.analyst_token
    if settings.reviewer_token:
        tokens["reviewer"] = settings.reviewer_token
    return tokens


def authenticated_role(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
) -> Role:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Bearer token required")
    tokens = _configured_tokens()
    if len(tokens) < 2:
        raise HTTPException(status_code=503, detail="Analyst and reviewer tokens must be configured")
    for role, token in tokens.items():
        if hmac.compare_digest(credentials.credentials, token):
            return role
    raise HTTPException(status_code=403, detail="Bearer token is not authorized")


def require_analyst(role: Role = Security(authenticated_role)) -> str:
    if role != "analyst":
        raise HTTPException(status_code=403, detail="Analyst role required")
    return role


def require_reviewer(role: Role = Security(authenticated_role)) -> str:
    if role != "reviewer":
        raise HTTPException(status_code=403, detail="Reviewer role required")
    return role
