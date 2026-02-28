from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel
from pydantic import ValidationError

from src.llm.mock import MockLLMClient
from src.utils.logging import get_logger


class LLMClient(Protocol):
    async def chat(self, system: str, user: str, json_schema: dict | None = None) -> str:
        ...

    def invoke_structured(
        self,
        request: StructuredPromptRequest,
        *,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        ...

    def invoke_parallel(
        self,
        requests: dict[str, StructuredPromptRequest],
        *,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class StructuredPromptRequest:
    system_template: str
    user_template: str
    input_values: dict[str, Any]
    output_model: type[BaseModel] | None = None
    output_schema: dict[str, Any] | None = None


_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Client cache (keyed by provider+model string)
# ---------------------------------------------------------------------------
_client_cache: dict[str, LLMClient] = {}


def _build_client(provider: str, model: str) -> LLMClient:
    """Instantiate an LLM client for the given provider and model."""
    cache_key = f"{provider}:{model}"
    if cache_key in _client_cache:
        return _client_cache[cache_key]

    client: LLMClient
    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            _logger.warning("anthropic_key_missing_fallback_mock")
            client = MockLLMClient()
        else:
            from src.llm.anthropic_client import AnthropicLLMClient
            client = AnthropicLLMClient(api_key=api_key, model=model)
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            _logger.warning("openai_key_missing_fallback_mock")
            client = MockLLMClient()
        else:
            from src.llm.openai_client import OpenAILLMClient
            client = OpenAILLMClient(api_key=api_key, model=model)
    else:
        # "mock" or unknown provider
        client = MockLLMClient()

    _client_cache[cache_key] = client
    return client


def _parse_provider_model(spec: str) -> tuple[str, str]:
    """Parse a ``provider:model`` string.  If no colon, infer the provider."""
    if ":" in spec:
        provider, _, model = spec.partition(":")
        return provider.strip(), model.strip()
    lower = spec.lower()
    if "claude" in lower or "anthropic" in lower:
        return "anthropic", spec
    if "mock" in lower:
        return "mock", spec
    # Default to openai
    return "openai", spec


# Task → env-var mapping for per-task model routing
_TASK_ENV_MAP: dict[str, str] = {
    "extraction": "LLM_EXTRACTION_MODEL",
    "report": "LLM_REPORT_MODEL",
    "validation": "LLM_VALIDATION_MODEL",
}


def get_llm_client(task: str | None = None) -> LLMClient:
    """Return the LLM client appropriate for *task*.

    Resolution order:
    1. Task-specific env var (e.g. ``LLM_EXTRACTION_MODEL=anthropic:claude-sonnet-4-20250514``)
    2. ``LLM_DEFAULT_MODEL`` env var (e.g. ``openai:gpt-4.1-mini``)
    3. Legacy ``OPENAI_API_KEY`` / ``OPENAI_MODEL`` combo
    4. ``MockLLMClient`` when no API key is found
    """
    # 1. Check task-specific override
    if task:
        env_var = _TASK_ENV_MAP.get(task, f"LLM_{task.upper()}_MODEL")
        spec = os.getenv(env_var, "")
        if spec:
            provider, model = _parse_provider_model(spec)
            return _build_client(provider, model)

    # 2. Check LLM_DEFAULT_MODEL
    default_spec = os.getenv("LLM_DEFAULT_MODEL", "")
    if default_spec and default_spec.lower() != "mock":
        provider, model = _parse_provider_model(default_spec)
        return _build_client(provider, model)

    # 3. Legacy: OPENAI_API_KEY
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        return _build_client("openai", model)

    # 4. Anthropic fallback
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        return _build_client("anthropic", model)

    return MockLLMClient()


@functools.lru_cache(maxsize=1)
def _build_llm_client() -> LLMClient:
    """Legacy single-client builder.  Delegates to :func:`get_llm_client`."""
    return get_llm_client()


def get_default_llm_client() -> LLMClient:
    return _build_llm_client()


def reset_llm_client() -> None:
    """Clear cached LLM clients. Useful for testing or configuration changes."""
    _build_llm_client.cache_clear()
    _client_cache.clear()


def validate_model(model_cls: type, data: dict[str, Any]) -> Any:
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        _logger.warning("llm_validation_error", extra={"doc_id": "-", "node_name": "llm", "elapsed_ms": 0, "error": str(exc)})
        raise


def langsmith_metadata(doc_id: str, node_name: str, **extra: Any) -> dict[str, Any]:
    metadata = {"doc_id": doc_id, "node_name": node_name}
    metadata.update(extra)
    return metadata
