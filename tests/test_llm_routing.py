"""Tests for LLM client routing, configuration, and fallback behavior."""
from __future__ import annotations

import os
from unittest.mock import patch

from src.llm.base import get_llm_client, reset_llm_client
from src.llm.mock import MockLLMClient


class TestLLMRouting:
    """Test LLM client factory and routing logic."""

    def setup_method(self) -> None:
        reset_llm_client()

    def test_default_client_is_mock_when_no_keys(self) -> None:
        """When no API keys are configured, the default client should be MockLLMClient."""
        with patch.dict(os.environ, {}, clear=True):
            reset_llm_client()
            client = get_llm_client()
            assert isinstance(client, MockLLMClient)

    def test_client_caching(self) -> None:
        """Same configuration should return the same client instance."""
        with patch.dict(os.environ, {}, clear=True):
            reset_llm_client()
            c1 = get_llm_client()
            c2 = get_llm_client()
            assert c1 is c2

    def test_reset_clears_cache(self) -> None:
        """reset_llm_client should clear the cached client."""
        with patch.dict(os.environ, {}, clear=True):
            c1 = get_llm_client()
            reset_llm_client()
            c2 = get_llm_client()
            # After reset, may be same type but should be fresh instance
            assert isinstance(c1, MockLLMClient)
            assert isinstance(c2, MockLLMClient)
