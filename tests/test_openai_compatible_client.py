from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.llm.base import StructuredPromptRequest
from src.llm.openai_client import OpenAILLMClient


class _StructuredAnswer(BaseModel):
    summary: str


class _FakeMessage:
    content = '{"summary":"ok"}'


class _FakeChoice:
    message = _FakeMessage()


class _FakeCompletion:
    choices = [_FakeChoice()]


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeCompletion:
        self.calls.append(kwargs)
        return _FakeCompletion()


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeResponses:
    def create(self, **_kwargs: Any) -> None:
        raise AssertionError("OpenAI-compatible fallback must not call responses.create")


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = _FakeChat()
        self.responses = _FakeResponses()


def test_deepseek_structured_output_uses_plain_chat_completion() -> None:
    client = OpenAILLMClient(api_key="test", model="deepseek-v4-flash", provider="deepseek")
    fake_client = _FakeOpenAI()
    client._client = fake_client  # type: ignore[assignment]
    client._chat_model = None

    result = client.invoke_structured(
        StructuredPromptRequest(
            system_template="You answer JSON.",
            user_template="Summarize {topic}.",
            input_values={"topic": "finance"},
            output_model=_StructuredAnswer,
        )
    )

    assert result.summary == "ok"
    assert len(fake_client.chat.completions.calls) == 1
    call = fake_client.chat.completions.calls[0]
    assert "response_format" not in call
    assert "JSON Schema" in call["messages"][1]["content"]