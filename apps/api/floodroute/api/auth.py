"""Small operator-only control plane. Registry credentials never reach the citizen app."""

from __future__ import annotations

import hmac
import json
import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException


def _registry() -> dict[str, str]:
    try:
        registry = json.loads(os.environ.get("FLOODROUTE_OPERATOR_TOKENS", ""))
        if not isinstance(registry, dict) or not registry or len(registry) > 100:
            raise ValueError
        if any(
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 128
            or not isinstance(token, str)
            or len(token) < 32
            or len(token) > 512
            or not token.isascii()
            or any(c.isspace() for c in token)
            for name, token in registry.items()
        ) or len(set(registry.values())) != len(registry):
            raise ValueError
        return registry
    except (TypeError, ValueError):
        raise HTTPException(503, "Operator administration is not configured") from None


def _identity(token: str | None) -> str:
    registry = _registry()
    if token and token.isascii():
        for name, expected in registry.items():
            if hmac.compare_digest(expected, token):
                return name
    raise HTTPException(
        401, "Valid operator credentials required", headers={"WWW-Authenticate": "Bearer"}
    )


def require_operator(authorization: Annotated[str | None, Header()] = None) -> str:
    """All registered identities are administrators; this is not a tenant account system."""
    scheme, _, token = (authorization or "").partition(" ")
    return _identity(token if scheme.lower() == "bearer" else None)


def bind_actor(claimed: str, operator: str) -> None:
    if claimed != operator:
        raise HTTPException(403, "operator_id must match the authenticated operator")


def authorize_route_profile(profile: str, authorization: str | None) -> None:
    if profile == "ambulance":
        require_operator(authorization)


def require_cosigner(
    claimed: str | None,
    operator: str,
    token: str | None,
) -> str:
    if not claimed or claimed.casefold() == operator.casefold():
        raise HTTPException(400, "Two distinct operators required for co-verification")
    second = _identity(token)
    if second.casefold() == operator.casefold() or second != claimed:
        raise HTTPException(403, "A distinct authenticated second operator must co-sign")
    return second


Operator = Annotated[str, Depends(require_operator)]
CoSignature = Annotated[str | None, Header(alias="X-FloodRoute-Co-Signature")]
