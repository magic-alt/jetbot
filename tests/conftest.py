"""Root conftest: ensure all tests use the mock LLM client."""

from __future__ import annotations

import pytest

from src.llm.base import reset_llm_client


@pytest.fixture(autouse=True)
def _force_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force mock LLM for every test to prevent real API calls."""
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "mock:mock")
    # Remove real API keys so fallback logic never reaches them
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Clear cached clients so the mock setting takes effect
    reset_llm_client()
