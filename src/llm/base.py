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


@functools.lru_cache(maxsize=1)
def _build_llm_client() -> LLMClient:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        from src.llm.openai_client import OpenAILLMClient

        return OpenAILLMClient(api_key=api_key, model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    return MockLLMClient()


def get_default_llm_client() -> LLMClient:
    return _build_llm_client()


def reset_llm_client() -> None:
    """Clear cached LLM client. Useful for testing or configuration changes."""
    _build_llm_client.cache_clear()


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
