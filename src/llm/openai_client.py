from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from openai import OpenAI

from src.llm.base import StructuredPromptRequest
from src.llm.token_manager import check_and_truncate
from src.llm.utils import parse_json_fallback, render_user_prompt
from src.utils.logging import get_logger

_logger = get_logger(__name__)

try:
    from langchain_core.messages import BaseMessage
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableParallel
    from langchain_openai import ChatOpenAI

    LANGCHAIN_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    BaseMessage = Any  # type: ignore[assignment,misc]
    ChatPromptTemplate = None  # type: ignore[assignment,misc]
    RunnableParallel = None  # type: ignore[assignment,misc]
    ChatOpenAI = None  # type: ignore[assignment,misc]
    LANGCHAIN_AVAILABLE = False


class OpenAILLMClient:
    def __init__(self, api_key: str, model: str, *, base_url: str | None = None, provider: str = "openai") -> None:
        _timeout = int(os.getenv("LLM_TIMEOUT_S", "60"))
        client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": float(_timeout)}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)
        self._model = model
        self._provider = provider.lower()
        self._chat_model = None
        if LANGCHAIN_AVAILABLE and ChatOpenAI is not None:
            chat_kwargs: dict[str, Any] = {
                "api_key": api_key,
                "model": model,
                "temperature": 0,
                "timeout": float(_timeout),
            }
            if base_url:
                chat_kwargs["base_url"] = base_url
            self._chat_model = ChatOpenAI(**chat_kwargs)

    async def chat(self, system: str, user: str, json_schema: dict | None = None) -> str:
        system, user = check_and_truncate(system, user, model=self._model)
        if self._chat_model is not None and ChatPromptTemplate is not None:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", "{system_message}"),
                    ("human", "{user_message}"),
                ]
            )
            chain = prompt | self._chat_model
            message = await chain.ainvoke({"system_message": system, "user_message": user})
            return _message_to_text(message)
        if json_schema and not self._supports_native_structured_output():
            user = _with_json_instructions(user, json_schema)
            json_schema = None
        return await asyncio.to_thread(self._chat_sync, system, user, json_schema)

    def _chat_sync(self, system: str, user: str, json_schema: dict | None) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if self._provider in {"deepseek", "ollama"}:
            completion = self._client.chat.completions.create(model=self._model, messages=messages)  # type: ignore[arg-type]
            return completion.choices[0].message.content or "{}"
        if json_schema:
            try:
                response = self._client.responses.create(  # type: ignore[call-overload]
                    model=self._model,
                    input=messages,
                    response_format={"type": "json_schema", "json_schema": json_schema},
                )
                return response.output_text
            except Exception as exc:
                _logger.warning("openai_json_schema_fallback", extra={"error": str(exc)})
        try:
            response = self._client.responses.create(model=self._model, input=messages)  # type: ignore[arg-type]
            return response.output_text
        except Exception as exc:
            _logger.warning("openai_responses_fallback", extra={"error": str(exc)})
            completion = self._client.chat.completions.create(model=self._model, messages=messages)  # type: ignore[arg-type]
            return completion.choices[0].message.content or "{}"

    def invoke_structured(
        self,
        request: StructuredPromptRequest,
        *,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        if self._supports_native_structured_output() and self._chat_model is not None and ChatPromptTemplate is not None:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", request.system_template),
                    ("human", request.user_template),
                ]
            )
            structured_schema = request.output_model or request.output_schema or {"type": "object", "properties": {}}
            chain = prompt | self._chat_model.with_structured_output(structured_schema)
            return chain.invoke(request.input_values, config=_runnable_config(run_name, tags, metadata))  # type: ignore[arg-type]

        json_schema: dict[str, Any] | None = request.output_schema
        if json_schema is None and request.output_model is not None:
            json_schema = request.output_model.model_json_schema()
        user_prompt = render_user_prompt(request.user_template, request.input_values)
        native_schema: dict[str, Any] | None = json_schema
        if json_schema is not None and not self._supports_native_structured_output():
            user_prompt = _with_json_instructions(user_prompt, json_schema)
            native_schema = None
        text = self._chat_sync(
            request.system_template,
            user_prompt,
            native_schema,
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
        if not requests:
            return {}
        if self._supports_native_structured_output() and self._chat_model is not None and ChatPromptTemplate is not None and RunnableParallel is not None:
            sample_input = next(iter(requests.values())).input_values
            if all(req.input_values == sample_input for req in requests.values()):
                chains: dict[str, Any] = {}
                for key, request in requests.items():
                    prompt = ChatPromptTemplate.from_messages(
                        [
                            ("system", request.system_template),
                            ("human", request.user_template),
                        ]
                    )
                    schema = request.output_model or request.output_schema or {"type": "object", "properties": {}}
                    chains[key] = prompt | self._chat_model.with_structured_output(schema)
                parallel = RunnableParallel(**chains)
                return parallel.invoke(sample_input, config=_runnable_config(run_name, tags, metadata))  # type: ignore[arg-type]

        # Different input_values: run in parallel using threads
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

    def _supports_native_structured_output(self) -> bool:
        return self._provider == "openai"


def _message_to_text(message: BaseMessage | str) -> str:
    if isinstance(message, str):
        return message
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, Mapping):
                text = item.get("text")
                if isinstance(text, str):
                    fragments.append(text)
        if fragments:
            return "\n".join(fragments)
    return "{}"


def _with_json_instructions(user_prompt: str, json_schema: dict[str, Any]) -> str:
    schema_text = json.dumps(json_schema, ensure_ascii=False)
    return (
        f"{user_prompt}\n\n"
        "Return only valid JSON matching this JSON Schema. "
        "Do not include markdown fences or explanatory text.\n"
        f"JSON Schema:\n{schema_text}"
    )


def _runnable_config(
    run_name: str | None,
    tags: list[str] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if run_name:
        config["run_name"] = run_name
    if tags:
        config["tags"] = tags
    if metadata:
        config["metadata"] = metadata
    return config
