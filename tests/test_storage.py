"""Tests for TaskStore (SQLite-backed) and LocalStore path validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.storage.task_store import TaskStore
from src.storage.local_store import LocalStore


class TestTaskStore:
    def test_create_and_get(self, tmp_path: Path):
        store = TaskStore(str(tmp_path))
        store.create("doc-1")
        task = store.get("doc-1")
        assert task is not None
        assert task["status"] == "queued"
        assert task["progress"] == 0

    def test_update(self, tmp_path: Path):
        store = TaskStore(str(tmp_path))
        store.create("doc-1")
        store.update("doc-1", status="running", progress=50)
        task = store.get("doc-1")
        assert task is not None
        assert task["status"] == "running"
        assert task["progress"] == 50

    def test_update_error_message(self, tmp_path: Path):
        store = TaskStore(str(tmp_path))
        store.create("doc-1")
        store.update("doc-1", status="failed", error_message="timeout")
        task = store.get("doc-1")
        assert task is not None
        assert task["error_message"] == "timeout"

    def test_get_nonexistent(self, tmp_path: Path):
        store = TaskStore(str(tmp_path))
        assert store.get("nonexistent") is None

    def test_concurrent_updates(self, tmp_path: Path):
        """Multiple creates/updates should not corrupt data."""
        store = TaskStore(str(tmp_path))
        for i in range(10):
            store.create(f"doc-{i}")
            store.update(f"doc-{i}", status="running", progress=i * 10)
        for i in range(10):
            task = store.get(f"doc-{i}")
            assert task is not None
            assert task["progress"] == i * 10


class TestLocalStorePathTraversal:
    def test_valid_doc_id(self, tmp_path: Path):
        store = LocalStore(str(tmp_path))
        path = store.doc_dir("valid-doc-123")
        # doc_dir returns path without creating; ensure_layout creates it
        assert not path.exists()
        store.ensure_layout("valid-doc-123")
        assert path.exists()

    def test_path_traversal_rejected(self, tmp_path: Path):
        store = LocalStore(str(tmp_path))
        with pytest.raises(ValueError, match="Invalid doc_id"):
            store.doc_dir("../../etc")

    def test_dot_rejected(self, tmp_path: Path):
        store = LocalStore(str(tmp_path))
        with pytest.raises(ValueError, match="Invalid doc_id"):
            store.doc_dir(".")

    def test_empty_rejected(self, tmp_path: Path):
        store = LocalStore(str(tmp_path))
        with pytest.raises(ValueError, match="Invalid doc_id"):
            store.doc_dir("")

    def test_slash_rejected(self, tmp_path: Path):
        store = LocalStore(str(tmp_path))
        with pytest.raises(ValueError, match="Invalid doc_id"):
            store.doc_dir("doc/sub")
