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


@dataclass(slots=True, frozen=True)
class LLMModelConfig:
    provider: str
    model: str
    source: str


_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Client cache (keyed by provider+model string)
# ---------------------------------------------------------------------------
_client_cache: dict[str, LLMClient] = {}


def _build_client(provider: str, model: str) -> LLMClient:
    """Instantiate an LLM client for the given provider and model."""
    provider = provider.lower()
    base_url = _provider_base_url(provider)
    cache_key = f"{provider}:{model}:{base_url or ''}"
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
    elif provider in {"openai", "deepseek", "ollama"}:
        api_key = _provider_api_key(provider)
        if provider != "ollama" and not api_key:
            _logger.warning("llm_key_missing_fallback_mock", extra={"provider": provider})
            client = MockLLMClient()
        else:
            from src.llm.openai_client import OpenAILLMClient

            client = OpenAILLMClient(api_key=api_key or "ollama", model=model, base_url=base_url)
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
    if "deepseek" in lower:
        return "deepseek", spec
    if "ollama" in lower:
        return "ollama", spec
    # Default to openai
    return "openai", spec


def _provider_api_key(provider: str) -> str:
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY", "")
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY", "")
    if provider == "ollama":
        return os.getenv("OLLAMA_API_KEY", "ollama")
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY", "")
    return ""


def _provider_base_url(provider: str) -> str | None:
    if provider == "openai":
        return os.getenv("OPENAI_BASE_URL", "").strip() or None
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip()
    if provider == "ollama":
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").strip()
    return None


def is_llm_provider_configured(provider: str) -> bool:
    provider = provider.lower()
    if provider == "mock":
        return True
    if provider == "ollama":
        return True
    return bool(_provider_api_key(provider))


# Task → env-var mapping for per-task model routing
_TASK_ENV_MAP: dict[str, str] = {
    "extraction": "LLM_EXTRACTION_MODEL",
    "report": "LLM_REPORT_MODEL",
    "validation": "LLM_VALIDATION_MODEL",
    "deep_analysis": "LLM_DEEP_ANALYSIS_MODEL",
}


def get_llm_model_config(task: str | None = None) -> LLMModelConfig:
    if task:
        env_var = _TASK_ENV_MAP.get(task, f"LLM_{task.upper()}_MODEL")
        spec = os.getenv(env_var, "")
        if spec:
            provider, model = _parse_provider_model(spec)
            return LLMModelConfig(provider=provider, model=model, source=env_var)

    default_spec = os.getenv("LLM_DEFAULT_MODEL", "")
    if default_spec:
        provider, model = _parse_provider_model(default_spec)
        return LLMModelConfig(provider=provider, model=model, source="LLM_DEFAULT_MODEL")

    if os.getenv("OPENAI_API_KEY", ""):
        return LLMModelConfig(
            provider="openai",
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            source="OPENAI_API_KEY",
        )

    if os.getenv("ANTHROPIC_API_KEY", ""):
        return LLMModelConfig(
            provider="anthropic",
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            source="ANTHROPIC_API_KEY",
        )

    return LLMModelConfig(provider="mock", model="mock", source="fallback")


def get_llm_client(task: str | None = None) -> LLMClient:
    """Return the LLM client appropriate for *task*.

    Resolution order:
    1. Task-specific env var (e.g. ``LLM_EXTRACTION_MODEL=anthropic:claude-sonnet-4-20250514``)
    2. ``LLM_DEFAULT_MODEL`` env var (e.g. ``openai:gpt-4.1-mini``)
    3. Legacy ``OPENAI_API_KEY`` / ``OPENAI_MODEL`` combo
    4. ``MockLLMClient`` when no API key is found
    """
    config = get_llm_model_config(task)
    return _build_client(config.provider, config.model)


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
        return model_cls.model_validate(data)  # type: ignore[attr-defined]
    except ValidationError as exc:
        _logger.warning("llm_validation_error", extra={"doc_id": "-", "node_name": "llm", "elapsed_ms": 0, "error": str(exc)})
        raise


def langsmith_metadata(doc_id: str, node_name: str, **extra: Any) -> dict[str, Any]:
    metadata = {"doc_id": doc_id, "node_name": node_name}
    metadata.update(extra)
    return metadata
