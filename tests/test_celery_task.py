"""Tests for Celery task queue module (src/tasks/)."""
from __future__ import annotations

import pytest

from src.tasks import is_celery_backend, CELERY_AVAILABLE


class TestIsCeleryBackend:
    def test_default_is_background(self, monkeypatch):
        monkeypatch.delenv("TASK_BACKEND", raising=False)
        assert is_celery_backend() is False

    def test_explicit_background(self, monkeypatch):
        monkeypatch.setenv("TASK_BACKEND", "background")
        assert is_celery_backend() is False

    def test_celery_backend_without_celery_installed(self, monkeypatch):
        monkeypatch.setenv("TASK_BACKEND", "celery")
        monkeypatch.setattr("src.tasks.CELERY_AVAILABLE", False)
        assert is_celery_backend() is False

    def test_celery_backend_with_celery_installed(self, monkeypatch):
        monkeypatch.setenv("TASK_BACKEND", "celery")
        monkeypatch.setattr("src.tasks.CELERY_AVAILABLE", True)
        assert is_celery_backend() is True


class TestAnalysisTaskStub:
    def test_run_analysis_import_does_not_crash(self):
        """Importing analysis module should not fail even without Celery."""
        from src.tasks.analysis import run_analysis
        assert run_analysis is not None

    def test_run_analysis_stub_raises_without_celery(self, monkeypatch):
        """If Celery is not available, calling the stub should raise RuntimeError."""
        if CELERY_AVAILABLE:
            pytest.skip("Celery is installed; stub test not applicable")
        from src.tasks.analysis import run_analysis
        with pytest.raises(RuntimeError, match="Celery is not configured"):
            run_analysis("test-doc", "/fake/path.pdf", {"doc_id": "test-doc"})
