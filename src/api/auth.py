from __future__ import annotations

import os
from typing import Annotated

from fastapi import Header, HTTPException


def _get_allowed_keys() -> set[str]:
    """Read comma-separated API keys from the API_KEYS env var.

    Returns an empty set when the var is not set, which disables auth.
    """
    raw = os.getenv("API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
) -> None:
    """FastAPI dependency that enforces API key authentication.

    - If ``API_KEYS`` env var is empty/unset, auth is disabled and every request passes.
    - Otherwise the request must supply a matching ``X-Api-Key`` header.
    """
    allowed = _get_allowed_keys()
    if not allowed:
        # Auth disabled — no keys configured
        return
    if not x_api_key or x_api_key not in allowed:
        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "data": None,
                "error": {
                    "code": "unauthorized",
                    "message": "Invalid or missing API key. Provide a valid X-Api-Key header.",
                },
            },
        )
