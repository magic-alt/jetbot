"""Shared utilities for LLM client implementations."""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError


def parse_json_fallback(text: str, output_model: type[BaseModel] | None) -> Any:
    """Attempt to extract and parse JSON from raw LLM output text.

    Tries:
    1. Direct model_validate_json
    2. Extract from markdown code fences
    3. Find first { ... } or [ ... ] block
    """
    # Try direct parse first
    if output_model is not None:
        try:
            return output_model.model_validate_json(text)
        except Exception:
            pass

    # Try parsing as raw JSON
    try:
        parsed: Any = json.loads(text.strip())
    except json.JSONDecodeError:
        parsed = None

    # Try extracting from markdown code fence
    if parsed is None:
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if fence_match:
            try:
                parsed = json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

    # Try finding JSON object or array
    if parsed is None:
        for pattern in (r"\{.*\}", r"\[.*\]"):
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    break
                except json.JSONDecodeError:
                    continue

    if parsed is None:
        if output_model is not None:
            raise ValueError(f"Could not parse JSON from LLM output for {output_model.__name__}")
        return {}

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


def render_user_prompt(template: str, values: dict[str, Any]) -> str:
    """Build a user prompt by formatting a template with the given values."""
    try:
        return template.format(**values)
    except KeyError:
        return template
