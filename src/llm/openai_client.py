from __future__ import annotations

import asyncio

from openai import OpenAI


class OpenAILLMClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    async def chat(self, system: str, user: str, json_schema: dict | None = None) -> str:
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
            except Exception:
                pass
        try:
            response = self._client.responses.create(model=self._model, input=messages)
            return response.output_text
        except Exception:
            completion = self._client.chat.completions.create(model=self._model, messages=messages)
            return completion.choices[0].message.content or "{}"
