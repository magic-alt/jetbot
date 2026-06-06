from __future__ import annotations

import functools
import os
import warnings
from typing import Annotated

from fastapi import Header, HTTPException

_auth_warning_issued = False


def _api_keys_env_signature() -> str:
    """Return the raw API_KEYS env value — used as lru_cache key so the
    cache automatically invalidates when the environment changes."""
    return os.getenv("API_KEYS", "")


@functools.lru_cache(maxsize=4)
def _get_allowed_keys(_env_signature: str = "") -> set[str]:
    """Read comma-separated API keys from the API_KEYS env var.

    The *_env_signature* parameter is the raw ``API_KEYS`` value; it is passed
    so that :func:`functools.lru_cache` creates a new cache entry whenever the
    environment variable changes (e.g. during tests with ``monkeypatch``).

    Returns an empty set when the var is not set, which disables auth.
    """
    return {k.strip() for k in _env_signature.split(",") if k.strip()}


def reset_auth_cache() -> None:
    """Clear the cached API keys (useful for testing)."""
    _get_allowed_keys.cache_clear()


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
) -> None:
    """FastAPI dependency that enforces API key authentication.

    - If ``API_KEYS`` env var is empty/unset, auth is disabled and every request passes.
    - In production (``ENV=production``), missing ``API_KEYS`` is a configuration error.
    - Otherwise the request must supply a matching ``X-Api-Key`` header.
    """
    global _auth_warning_issued
    env_sig = _api_keys_env_signature()
    allowed = _get_allowed_keys(env_sig)
    if not allowed:
        if os.getenv("ENV", "").lower() == "production":
            raise HTTPException(
                status_code=500,
                detail={
                    "ok": False,
                    "data": None,
                    "error": {
                        "code": "misconfigured",
                        "message": "API_KEYS must be set in production.",
                    },
                },
            )
        if not _auth_warning_issued:
            warnings.warn(
                "API_KEYS is not set — authentication is disabled. "
                "Set API_KEYS before deploying to production.",
                stacklevel=2,
            )
            _auth_warning_issued = True
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
