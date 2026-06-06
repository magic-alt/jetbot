"""Anthropic Claude LLM client -- drop-in replacement for OpenAILLMClient.

Requires: ``pip install anthropic``
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from src.llm.base import StructuredPromptRequest
from src.llm.token_manager import check_and_truncate
from src.llm.utils import parse_json_fallback, render_user_prompt
from src.utils.logging import get_logger

_logger = get_logger(__name__)

# Configurable max output tokens for Anthropic API calls.
_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))

try:
    from anthropic import Anthropic  # type: ignore[import-untyped]

    ANTHROPIC_AVAILABLE = True
except Exception:  # pragma: no cover
    Anthropic = None  # type: ignore[assignment,misc]
    ANTHROPIC_AVAILABLE = False


class AnthropicLLMClient:
    """Anthropic Claude API client implementing the ``LLMClient`` protocol."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        if not ANTHROPIC_AVAILABLE or Anthropic is None:
            raise RuntimeError("anthropic package is not installed. Run: pip install anthropic")
        _timeout = int(os.getenv("LLM_TIMEOUT_S", "60"))
        self._client = Anthropic(api_key=api_key, timeout=float(_timeout))
        self._model = model

    async def chat(self, system: str, user: str, json_schema: dict | None = None) -> str:
        system, user = check_and_truncate(system, user, model=self._model)
        return await asyncio.to_thread(self._chat_sync, system, user, json_schema)

    def _chat_sync(self, system: str, user: str, json_schema: dict | None) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text  # type: ignore[union-attr]
        except Exception as exc:
            _logger.warning("anthropic_chat_error", extra={"error": str(exc)})
            return "{}"

    def invoke_structured(
        self,
        request: StructuredPromptRequest,
        *,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        schema = request.output_schema
        if schema is None and request.output_model is not None:
            schema = request.output_model.model_json_schema()
        text = self._chat_sync(
            request.system_template,
            render_user_prompt(request.user_template, request.input_values),
            schema,
        )
        return parse_json_fallback(text, request.output_model)

    def invoke_parallel(
        self,
        requests: dict[str, StructuredPromptRequest],
        *,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not requests:
            return {}
        results: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=min(len(requests), 4)) as pool:
            futures = {
                pool.submit(
                    self.invoke_structured,
                    request,
                    run_name=f"{run_name}.{key}" if run_name else key,
                    tags=tags,
                    metadata=metadata,
                ): key
                for key, request in requests.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                results[key] = future.result()
        return results
