"""Tests for S3/local object store (src/storage/object_store.py)."""
from __future__ import annotations


from src.storage.object_store import ObjectStore


class TestObjectStoreLocal:
    """ObjectStore without S3 credentials should use local filesystem."""

    def test_defaults_to_local(self, tmp_path):
        store = ObjectStore(local_dir=str(tmp_path))
        assert store.is_s3 is False

    def test_put_and_get(self, tmp_path):
        store = ObjectStore(local_dir=str(tmp_path))
        url = store.put("docs/test1/raw.pdf", b"%PDF-1.4 content")
        assert "test1" in url
        data = store.get("docs/test1/raw.pdf")
        assert data == b"%PDF-1.4 content"

    def test_get_missing_returns_none(self, tmp_path):
        store = ObjectStore(local_dir=str(tmp_path))
        assert store.get("nonexistent/file.bin") is None

    def test_exists(self, tmp_path):
        store = ObjectStore(local_dir=str(tmp_path))
        assert store.exists("foo/bar.bin") is False
        store.put("foo/bar.bin", b"data")
        assert store.exists("foo/bar.bin") is True

    def test_delete(self, tmp_path):
        store = ObjectStore(local_dir=str(tmp_path))
        store.put("to_delete.bin", b"data")
        assert store.exists("to_delete.bin") is True
        result = store.delete("to_delete.bin")
        assert result is True
        assert store.exists("to_delete.bin") is False

    def test_delete_missing(self, tmp_path):
        store = ObjectStore(local_dir=str(tmp_path))
        assert store.delete("nonexistent.bin") is False

    def test_nested_path_creates_dirs(self, tmp_path):
        store = ObjectStore(local_dir=str(tmp_path))
        store.put("a/b/c/d/file.bin", b"nested data")
        data = store.get("a/b/c/d/file.bin")
        assert data == b"nested data"

    def test_overwrite_existing(self, tmp_path):
        store = ObjectStore(local_dir=str(tmp_path))
        store.put("test.bin", b"v1")
        store.put("test.bin", b"v2")
        assert store.get("test.bin") == b"v2"
