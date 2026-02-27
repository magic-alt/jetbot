from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from src.llm.base import StructuredPromptRequest
from src.utils.logging import get_logger

_logger = get_logger(__name__)

try:
    from langchain_core.messages import BaseMessage
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableParallel
    from langchain_openai import ChatOpenAI

    LANGCHAIN_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    BaseMessage = Any  # type: ignore[assignment]
    ChatPromptTemplate = None  # type: ignore[assignment]
    RunnableParallel = None  # type: ignore[assignment]
    ChatOpenAI = None  # type: ignore[assignment]
    LANGCHAIN_AVAILABLE = False


class OpenAILLMClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._chat_model = None
        if LANGCHAIN_AVAILABLE and ChatOpenAI is not None:
            self._chat_model = ChatOpenAI(
                api_key=api_key,
                model=model,
                temperature=0,
            )

    async def chat(self, system: str, user: str, json_schema: dict | None = None) -> str:
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
        return await asyncio.to_thread(self._chat_sync, system, user, json_schema)

    def _chat_sync(self, system: str, user: str, json_schema: dict | None) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if json_schema:
            try:
                response = self._client.responses.create(
                    model=self._model,
                    input=messages,
                    response_format={"type": "json_schema", "json_schema": json_schema},
                )
                return response.output_text
            except Exception as exc:
                _logger.warning("openai_json_schema_fallback", extra={"error": str(exc)})
        try:
            response = self._client.responses.create(model=self._model, input=messages)
            return response.output_text
        except Exception as exc:
            _logger.warning("openai_responses_fallback", extra={"error": str(exc)})
            completion = self._client.chat.completions.create(model=self._model, messages=messages)
            return completion.choices[0].message.content or "{}"

    def invoke_structured(
        self,
        request: StructuredPromptRequest,
        *,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        if self._chat_model is not None and ChatPromptTemplate is not None:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", request.system_template),
                    ("human", request.user_template),
                ]
            )
            schema = request.output_model or request.output_schema or {"type": "object", "properties": {}}
            chain = prompt | self._chat_model.with_structured_output(schema)
            return chain.invoke(request.input_values, config=_runnable_config(run_name, tags, metadata))

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
        if not requests:
            return {}
        if self._chat_model is not None and ChatPromptTemplate is not None and RunnableParallel is not None:
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
                return parallel.invoke(sample_input, config=_runnable_config(run_name, tags, metadata))

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


def _render_user_prompt(template: str, values: dict[str, Any]) -> str:
    try:
        return template.format(**values)
    except KeyError as exc:
        _logger.warning("user_prompt_missing_key", extra={"key": str(exc), "template_keys": list(values.keys())})
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
