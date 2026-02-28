"""Token counting, truncation, and prompt splitting utilities.

Uses ``tiktoken`` for accurate OpenAI token counts when available,
falling back to a simple character-based estimate (1 token ≈ 4 chars for
English, ≈ 2 chars for CJK).
"""

from __future__ import annotations

import os
import re
from typing import Any

from src.utils.logging import get_logger

_logger = get_logger(__name__)

try:
    import tiktoken  # type: ignore[import-untyped]

    TIKTOKEN_AVAILABLE = True
except Exception:  # pragma: no cover
    tiktoken = None  # type: ignore[assignment]
    TIKTOKEN_AVAILABLE = False

_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")

# Default model context windows (tokens)
_MODEL_LIMITS: dict[str, int] = {
    "gpt-4.1": 1047576,
    "gpt-4.1-mini": 1047576,
    "gpt-4.1-nano": 1047576,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16384,
    "claude-sonnet-4-20250514": 200000,
    "claude-opus-4-20250514": 200000,
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-haiku-20240307": 200000,
}


def get_model_limit(model: str | None = None) -> int:
    """Return the context window size for *model* (defaults to ``MODEL_MAX_TOKENS`` env var)."""
    env_limit = os.getenv("MODEL_MAX_TOKENS", "")
    if env_limit:
        try:
            return int(env_limit)
        except ValueError:
            pass
    if model:
        for key, limit in _MODEL_LIMITS.items():
            if key in model:
                return limit
    return 128000  # safe default


def count_tokens(text: str, model: str | None = None) -> int:
    """Count the number of tokens in *text*.

    When ``tiktoken`` is available and the model is an OpenAI model, uses the
    exact tokeniser.  Otherwise falls back to a heuristic.
    """
    if TIKTOKEN_AVAILABLE and tiktoken is not None:
        try:
            enc = tiktoken.encoding_for_model(model or "gpt-4o")
            return len(enc.encode(text))
        except Exception:
            pass
    return _estimate_tokens(text)


def truncate_to_fit(
    text: str,
    max_tokens: int,
    *,
    model: str | None = None,
    reserve_output: int = 1024,
) -> str:
    """Truncate *text* so that it fits within *max_tokens* minus *reserve_output*.

    Returns the (possibly shortened) text.
    """
    budget = max_tokens - reserve_output
    if budget <= 0:
        return ""

    current = count_tokens(text, model)
    if current <= budget:
        return text

    # Binary-search for the right cutoff length
    ratio = budget / current
    cut = int(len(text) * ratio * 0.95)  # slightly conservative
    while count_tokens(text[:cut], model) > budget and cut > 0:
        cut = int(cut * 0.9)
    _logger.info(
        "token_truncated",
        extra={"original_tokens": current, "budget": budget, "cut_chars": cut},
    )
    return text[:cut]


def split_prompt(
    text: str,
    max_tokens: int,
    *,
    model: str | None = None,
    overlap_tokens: int = 100,
) -> list[str]:
    """Split *text* into chunks each fitting within *max_tokens*.

    Adjacent chunks share approximately *overlap_tokens* worth of text to
    preserve context boundaries.
    """
    total = count_tokens(text, model)
    if total <= max_tokens:
        return [text]

    # Estimate chars-per-token for this text
    cpt = len(text) / max(total, 1)
    chunk_chars = int(max_tokens * cpt * 0.95)
    overlap_chars = int(overlap_tokens * cpt)

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        parts.append(text[start:end])
        start = end - overlap_chars if end < len(text) else end

    return parts


def check_and_truncate(
    system: str,
    user: str,
    *,
    model: str | None = None,
    reserve_output: int = 1024,
) -> tuple[str, str]:
    """Ensure *system* + *user* fits the model context.

    If the combined prompt is too long, the *user* portion is truncated
    (system prompts are typically much shorter and should remain intact).
    Returns ``(system, user)`` — possibly with *user* shortened.
    """
    limit = get_model_limit(model)
    sys_tokens = count_tokens(system, model)
    user_budget = limit - sys_tokens - reserve_output
    if user_budget <= 0:
        _logger.warning("system_prompt_exceeds_limit", extra={"sys_tokens": sys_tokens, "limit": limit})
        return system, ""
    user_truncated = truncate_to_fit(user, user_budget + reserve_output, model=model, reserve_output=reserve_output)
    return system, user_truncated


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Heuristic: ~4 chars/token for English, ~2 chars/token for CJK."""
    cjk_count = len(_CJK_RANGE.findall(text))
    non_cjk = len(text) - cjk_count
    return int(cjk_count / 1.5 + non_cjk / 4)
