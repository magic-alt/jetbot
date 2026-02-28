"""Anthropic Claude LLM client — drop-in replacement for OpenAILLMClient.

Requires: ``pip install anthropic``
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from pydantic import ValidationError

from src.llm.base import StructuredPromptRequest
from src.llm.token_manager import check_and_truncate
from src.utils.logging import get_logger

_logger = get_logger(__name__)

try:
    from anthropic import Anthropic  # type: ignore[import-untyped]

    ANTHROPIC_AVAILABLE = True
except Exception:  # pragma: no cover
    Anthropic = None  # type: ignore[assignment]
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
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text
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
            _render_user_prompt(request.user_template, request.input_values),
            schema,
        )
        return _parse_fallback(text, request.output_model)

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


# ---------------------------------------------------------------------------
# Helpers (mirrored from openai_client for consistency)
# ---------------------------------------------------------------------------


def _render_user_prompt(template: str, values: dict[str, Any]) -> str:
    try:
        return template.format(**values)
    except KeyError as exc:
        _logger.warning("user_prompt_missing_key", extra={"key": str(exc)})
        return template


def _parse_fallback(text: str, output_model: Any) -> Any:
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError:
        parsed = {}
    if output_model is None:
        return parsed
    try:
        return output_model.model_validate(parsed)
    except ValidationError:
        if isinstance(parsed, list):
            fields = list(output_model.model_fields.keys())
            if len(fields) == 1:
                return output_model.model_validate({fields[0]: parsed})
        raise
