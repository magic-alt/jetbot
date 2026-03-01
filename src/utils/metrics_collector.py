"""Prometheus metrics collector for the Financial Report Agent."""
from __future__ import annotations

# Try to import prometheus_client; provide no-op fallback if not installed
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False

class MetricsCollector:
    """Collects application metrics. Falls back to no-op if prometheus_client is not installed."""

    def __init__(self) -> None:
        if _HAS_PROMETHEUS:
            self.pipeline_runs = Counter("pipeline_runs_total", "Total pipeline runs", ["status"])
            self.pipeline_duration = Histogram("pipeline_duration_seconds", "Pipeline duration in seconds", buckets=[1, 5, 10, 30, 60, 120, 300])
            self.node_duration = Histogram("node_duration_seconds", "Per-node duration in seconds", ["node_name"], buckets=[0.5, 1, 5, 10, 30, 60])
            self.llm_calls = Counter("llm_calls_total", "Total LLM API calls", ["model", "status"])
            self.llm_tokens = Counter("llm_tokens_total", "Total tokens used", ["model", "direction"])
            self.active_analyses = Gauge("active_analyses", "Currently running analyses")
            self.pdf_pages = Histogram("pdf_pages_total", "PDF page count per document", buckets=[1, 5, 10, 25, 50, 100, 200])
        self._enabled = _HAS_PROMETHEUS

    def record_pipeline_run(self, status: str = "success") -> None:
        if self._enabled:
            self.pipeline_runs.labels(status=status).inc()

    def record_pipeline_duration(self, seconds: float) -> None:
        if self._enabled:
            self.pipeline_duration.observe(seconds)

    def record_node_duration(self, node_name: str, seconds: float) -> None:
        if self._enabled:
            self.node_duration.labels(node_name=node_name).observe(seconds)

    def record_llm_call(self, model: str, status: str = "success") -> None:
        if self._enabled:
            self.llm_calls.labels(model=model, status=status).inc()

    def record_llm_tokens(self, model: str, input_tokens: int, output_tokens: int) -> None:
        if self._enabled:
            self.llm_tokens.labels(model=model, direction="input").inc(input_tokens)
            self.llm_tokens.labels(model=model, direction="output").inc(output_tokens)

    def set_active_analyses(self, count: int) -> None:
        if self._enabled:
            self.active_analyses.set(count)

    def record_pdf_pages(self, count: int) -> None:
        if self._enabled:
            self.pdf_pages.observe(count)

    def generate_metrics(self) -> bytes:
        """Generate Prometheus-format metrics output."""
        if self._enabled:
            return generate_latest()
        return b"# prometheus_client not installed\n"

    @property
    def content_type(self) -> str:
        if self._enabled:
            return CONTENT_TYPE_LATEST
        return "text/plain"

# Singleton instance
metrics = MetricsCollector()
