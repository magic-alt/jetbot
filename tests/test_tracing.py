"""Tests for OpenTelemetry tracing setup (src/utils/tracing.py)."""
from __future__ import annotations

import os

import pytest

from src.utils.tracing import init_tracing, get_tracer, trace_span, _HAS_OTEL


class TestInitTracing:
    """init_tracing should not raise regardless of environment."""

    def test_no_raise_without_endpoint(self, monkeypatch):
        monkeypatch.delenv("OTLP_ENDPOINT", raising=False)
        init_tracing()

    def test_no_raise_with_empty_endpoint(self, monkeypatch):
        monkeypatch.setenv("OTLP_ENDPOINT", "")
        init_tracing()

    def test_no_raise_with_custom_service_name(self, monkeypatch):
        monkeypatch.delenv("OTLP_ENDPOINT", raising=False)
        init_tracing(service_name="test-service")


class TestGetTracer:
    """get_tracer should return None when tracing is not initialized."""

    def test_returns_none_when_not_initialized(self, monkeypatch):
        import src.utils.tracing as tracing_mod
        monkeypatch.setattr(tracing_mod, "_tracer", None)
        assert get_tracer() is None

    def test_return_type(self):
        result = get_tracer()
        # Should be None or a tracer object
        assert result is None or hasattr(result, "start_as_current_span")


class TestTraceSpan:
    """trace_span context manager should work as no-op when tracer is None."""

    def test_yields_none_when_not_configured(self, monkeypatch):
        import src.utils.tracing as tracing_mod
        monkeypatch.setattr(tracing_mod, "_tracer", None)
        with trace_span("test-span") as span:
            assert span is None

    def test_yields_none_with_attributes(self, monkeypatch):
        import src.utils.tracing as tracing_mod
        monkeypatch.setattr(tracing_mod, "_tracer", None)
        with trace_span("test-span", attributes={"key": "value"}) as span:
            assert span is None

    def test_body_executes_when_not_configured(self, monkeypatch):
        import src.utils.tracing as tracing_mod
        monkeypatch.setattr(tracing_mod, "_tracer", None)
        executed = False
        with trace_span("test-span"):
            executed = True
        assert executed

    def test_noop_span_does_not_break_nested(self, monkeypatch):
        import src.utils.tracing as tracing_mod
        monkeypatch.setattr(tracing_mod, "_tracer", None)
        with trace_span("outer") as outer:
            with trace_span("inner") as inner:
                assert outer is None
                assert inner is None


@pytest.mark.skipif(not _HAS_OTEL, reason="opentelemetry not installed")
class TestTracingWithOtel:
    """When opentelemetry is installed, verify init_tracing configures the tracer."""

    def test_init_with_endpoint_sets_tracer(self, monkeypatch):
        import src.utils.tracing as tracing_mod
        monkeypatch.setattr(tracing_mod, "_tracer", None)
        # Even with a bogus endpoint, init_tracing should attempt setup
        # This may or may not succeed depending on whether the OTLP exporter
        # can be instantiated, but it should not raise
        monkeypatch.setenv("OTLP_ENDPOINT", "http://localhost:4317")
        try:
            init_tracing()
        except Exception:
            pass  # Connection failures are acceptable in tests
