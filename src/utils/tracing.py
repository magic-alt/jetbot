"""OpenTelemetry tracing setup."""
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Any, Generator

_tracer = None
_HAS_OTEL = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _HAS_OTEL = True
except ImportError:
    pass


def init_tracing(service_name: str = "financial-report-agent") -> None:
    """Initialize OpenTelemetry tracing if configured."""
    global _tracer, _HAS_OTEL

    endpoint = os.getenv("OTLP_ENDPOINT")
    if not endpoint or not _HAS_OTEL:
        return

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider = TracerProvider()
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
    except Exception:
        _tracer = None


def get_tracer():
    """Return the OpenTelemetry tracer, or None if not configured."""
    return _tracer


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Generator:
    """Context manager that creates a trace span if tracing is enabled."""
    if _tracer is not None:
        with _tracer.start_as_current_span(name, attributes=attributes or {}) as span:
            yield span
    else:
        yield None
