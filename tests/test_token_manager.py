"""Tests for token counting and truncation (src/llm/token_manager.py)."""
from __future__ import annotations

from src.llm.token_manager import (
    count_tokens,
    truncate_to_fit,
    split_prompt,
    check_and_truncate,
    get_model_limit,
    _estimate_tokens,
)


class TestCountTokens:
    def test_english_text_returns_positive(self):
        n = count_tokens("Hello world, this is a test sentence.")
        assert n > 0

    def test_empty_string_returns_zero(self):
        assert count_tokens("") == 0

    def test_cjk_text_returns_reasonable_count(self):
        text = "这是一个测试句子用于验证中文分词"
        n = count_tokens(text)
        assert n > 5  # Should be more than a few tokens


class TestEstimateTokens:
    def test_english_estimate(self):
        text = "The quick brown fox jumps over the lazy dog"
        est = _estimate_tokens(text)
        assert 8 <= est <= 15

    def test_cjk_estimate_higher_density(self):
        text = "中文测试"
        est = _estimate_tokens(text)
        assert est >= 2

    def test_empty(self):
        assert _estimate_tokens("") == 0


class TestTruncateToFit:
    def test_short_text_unchanged(self):
        text = "short"
        result = truncate_to_fit(text, 1000, reserve_output=0)
        assert result == text

    def test_long_text_truncated(self):
        text = "word " * 10000  # very long
        result = truncate_to_fit(text, 100, reserve_output=10)
        assert len(result) < len(text)
        assert count_tokens(result) <= 100

    def test_zero_budget_returns_empty(self):
        result = truncate_to_fit("hello", max_tokens=10, reserve_output=20)
        assert result == ""


class TestSplitPrompt:
    def test_short_text_single_chunk(self):
        text = "short text"
        parts = split_prompt(text, 1000)
        assert len(parts) == 1
        assert parts[0] == text

    def test_long_text_multiple_chunks(self):
        text = "word " * 5000
        parts = split_prompt(text, 500)
        assert len(parts) > 1
        # Reassembled text should cover original
        combined = "".join(parts)
        assert len(combined) >= len(text) * 0.9


class TestCheckAndTruncate:
    def test_fits_within_limit(self):
        sys, usr = check_and_truncate("system", "user", model="gpt-4o")
        assert sys == "system"
        assert usr == "user"

    def test_long_user_truncated(self):
        system = "Be helpful."
        user = "x " * 200000
        sys_out, usr_out = check_and_truncate(system, user, model="gpt-4o")
        assert sys_out == system
        assert len(usr_out) < len(user)


class TestGetModelLimit:
    def test_known_model(self):
        assert get_model_limit("gpt-4o") == 128000

    def test_unknown_model_default(self):
        assert get_model_limit("unknown-model-xyz") == 128000

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MODEL_MAX_TOKENS", "32000")
        assert get_model_limit("gpt-4o") == 32000
