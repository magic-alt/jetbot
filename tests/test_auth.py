"""Tests for API key authentication (src/api/auth.py)."""
from __future__ import annotations


import pytest
from fastapi import HTTPException


def _import_verify():
    from src.api.auth import verify_api_key
    return verify_api_key


class TestVerifyApiKey:
    """Tests for the verify_api_key FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_no_keys_configured_always_passes(self, monkeypatch):
        """When API_KEYS is empty, every request is allowed."""
        monkeypatch.setenv("API_KEYS", "")
        verify = _import_verify()
        # Should not raise regardless of header value
        await verify(x_api_key=None)
        await verify(x_api_key="anything")

    @pytest.mark.asyncio
    async def test_valid_key_passes(self, monkeypatch):
        """A matching key must be accepted."""
        monkeypatch.setenv("API_KEYS", "secret-key-1,secret-key-2")
        verify = _import_verify()
        await verify(x_api_key="secret-key-1")
        await verify(x_api_key="secret-key-2")

    @pytest.mark.asyncio
    async def test_invalid_key_raises_401(self, monkeypatch):
        """A wrong key must produce a 401 response."""
        monkeypatch.setenv("API_KEYS", "secret-key-1")
        verify = _import_verify()
        with pytest.raises(HTTPException) as exc_info:
            await verify(x_api_key="wrong-key")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_key_raises_401(self, monkeypatch):
        """A missing key header must produce a 401 response."""
        monkeypatch.setenv("API_KEYS", "secret-key-1")
        verify = _import_verify()
        with pytest.raises(HTTPException) as exc_info:
            await verify(x_api_key=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_whitespace_keys_ignored(self, monkeypatch):
        """Whitespace-only entries in API_KEYS must be ignored."""
        monkeypatch.setenv("API_KEYS", " , , ")
        verify = _import_verify()
        # All entries are whitespace → treated as empty → auth disabled
        await verify(x_api_key=None)

    @pytest.mark.asyncio
    async def test_key_trimmed_from_env(self, monkeypatch):
        """Keys with surrounding spaces in API_KEYS should still match."""
        monkeypatch.setenv("API_KEYS", "  mykey  ,  other  ")
        verify = _import_verify()
        await verify(x_api_key="mykey")
        await verify(x_api_key="other")
