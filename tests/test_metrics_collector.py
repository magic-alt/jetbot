"""Tests for MetricsCollector (src/utils/metrics_collector.py)."""
from __future__ import annotations

import pytest

from src.utils.metrics_collector import MetricsCollector, metrics, _HAS_PROMETHEUS


class TestMetricsCollectorInit:
    """MetricsCollector should initialize without error regardless of prometheus_client."""

    def test_init_no_error(self):
        assert metrics._enabled == _HAS_PROMETHEUS

    def test_enabled_matches_prometheus_availability(self):
        assert isinstance(metrics._enabled, bool)


class TestNoOpSafety:
    """All record methods must be callable without raising, even when prometheus_client is absent."""

    def test_record_pipeline_run(self):
        metrics.record_pipeline_run("success")
        metrics.record_pipeline_run("failure")

    def test_record_pipeline_duration(self):
        metrics.record_pipeline_duration(1.5)

    def test_record_node_duration(self):
        metrics.record_node_duration("extract", 0.8)
        metrics.record_node_duration("transform", 2.3)

    def test_record_llm_call(self):
        metrics.record_llm_call("gpt-4o", "success")
        metrics.record_llm_call("gpt-4o", "error")

    def test_record_llm_tokens(self):
        metrics.record_llm_tokens("gpt-4o", input_tokens=100, output_tokens=50)

    def test_set_active_analyses(self):
        metrics.set_active_analyses(3)
        metrics.set_active_analyses(0)

    def test_record_pdf_pages(self):
        metrics.record_pdf_pages(42)


class TestGenerateMetrics:
    """generate_metrics must return bytes; content_type must return a string."""

    def test_generate_metrics_returns_bytes(self):
        result = metrics.generate_metrics()
        assert isinstance(result, bytes)

    def test_content_type_is_string(self):
        assert isinstance(metrics.content_type, str)

    def test_generate_metrics_not_empty(self):
        result = metrics.generate_metrics()
        assert len(result) > 0


class TestSingletonInstance:
    """The module-level `metrics` singleton should be usable."""

    def test_singleton_importable(self):
        from src.utils.metrics_collector import metrics as m
        assert isinstance(m, MetricsCollector)

    def test_singleton_record_methods(self):
        from src.utils.metrics_collector import metrics as m
        # Should not raise
        m.record_pipeline_run()
        m.record_pipeline_duration(0.1)
        m.record_node_duration("test_node", 0.05)


@pytest.mark.skipif(not _HAS_PROMETHEUS, reason="prometheus_client not installed")
class TestPrometheusCounters:
    """When prometheus_client is available, verify counters increment correctly."""

    def test_pipeline_runs_counter_increments(self):
        before = metrics.pipeline_runs.labels(status="success")._value.get()
        metrics.record_pipeline_run("success")
        after = metrics.pipeline_runs.labels(status="success")._value.get()
        assert after == before + 1

    def test_llm_calls_counter_increments(self):
        before = metrics.llm_calls.labels(model="test-model", status="success")._value.get()
        metrics.record_llm_call("test-model", "success")
        after = metrics.llm_calls.labels(model="test-model", status="success")._value.get()
        assert after == before + 1

    def test_llm_tokens_counter_increments(self):
        before_in = metrics.llm_tokens.labels(model="test-model", direction="input")._value.get()
        before_out = metrics.llm_tokens.labels(model="test-model", direction="output")._value.get()
        metrics.record_llm_tokens("test-model", input_tokens=100, output_tokens=50)
        after_in = metrics.llm_tokens.labels(model="test-model", direction="input")._value.get()
        after_out = metrics.llm_tokens.labels(model="test-model", direction="output")._value.get()
        assert after_in == before_in + 100
        assert after_out == before_out + 50

    def test_active_analyses_gauge(self):
        metrics.set_active_analyses(5)
        assert metrics.active_analyses._value.get() == 5
        metrics.set_active_analyses(0)
        assert metrics.active_analyses._value.get() == 0

    def test_generate_metrics_contains_metric_names(self):
        metrics.record_pipeline_run("success")
        output = metrics.generate_metrics().decode()
        assert "pipeline_runs_total" in output
