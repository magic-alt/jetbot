"""Tests for the Hermes external agent adapter."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestHermesAdapter:
    """Test HermesAgentClient configuration and error handling."""

    def test_client_returns_none_when_url_not_set(self) -> None:
        """When HERMES_AGENT_URL is not set, get_hermes_agent_client should return None."""
        with patch.dict(os.environ, {"HERMES_AGENT_URL": ""}, clear=False):
            from src.agent.adapters.hermes import get_hermes_agent_client
            client = get_hermes_agent_client()
            assert client is None

    def test_client_created_when_url_set(self) -> None:
        """When HERMES_AGENT_URL is set, a client should be created."""
        with patch.dict(os.environ, {"HERMES_AGENT_URL": "http://localhost:9999"}, clear=False):
            from src.agent.adapters.hermes import HermesAgentClient, get_hermes_agent_client
            client = get_hermes_agent_client()
            assert client is not None
            assert isinstance(client, HermesAgentClient)

    def test_client_http_error_handling(self) -> None:
        """When Hermes returns an HTTP error, analyze should raise RuntimeError."""
        import urllib.error
        from unittest.mock import MagicMock

        with patch.dict(os.environ, {"HERMES_AGENT_URL": "http://localhost:9999"}, clear=False):
            from src.agent.adapters.hermes import get_hermes_agent_client
            client = get_hermes_agent_client()
            assert client is not None

            mock_context = MagicMock()
            mock_context.model_dump.return_value = {}

            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = urllib.error.HTTPError(
                    url="http://localhost:9999/analyze",
                    code=500,
                    msg="Internal Server Error",
                    hdrs=None,  # type: ignore[arg-type]
                    fp=None,
                )
                with pytest.raises(RuntimeError, match="Hermes agent returned HTTP 500"):
                    client.analyze(mock_context, task="deep_analysis")
