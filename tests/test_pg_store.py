"""Tests for PgStore and StorageBackend protocol (src/storage/pg_store.py, backend.py)."""
from __future__ import annotations


from src.schemas.models import DocumentMeta
from src.storage.backend import StorageBackend, get_storage_backend
from src.storage.local_store import LocalStore
from src.storage.pg_store import PgStore


class TestStorageBackendProtocol:
    def test_local_store_satisfies_protocol(self):
        """LocalStore should satisfy the StorageBackend protocol."""
        assert isinstance(LocalStore(), StorageBackend)

    def test_pg_store_satisfies_protocol(self):
        """PgStore should satisfy the StorageBackend protocol."""
        store = PgStore(database_url="", local_fallback_dir="data")
        assert isinstance(store, StorageBackend)


class TestGetStorageBackend:
    def test_default_returns_local(self, monkeypatch):
        monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        backend = get_storage_backend()
        assert isinstance(backend, LocalStore)

    def test_explicit_local(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        backend = get_storage_backend()
        assert isinstance(backend, LocalStore)

    def test_postgres_without_url_falls_back(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "postgres")
        monkeypatch.setenv("DATABASE_URL", "")
        backend = get_storage_backend()
        assert isinstance(backend, PgStore)


class TestPgStoreFallback:
    """PgStore without a real database URL should work via local filesystem."""

    def test_save_and_load_meta(self, tmp_path):
        store = PgStore(database_url="", local_fallback_dir=str(tmp_path))
        meta = DocumentMeta(doc_id="test-pg-1", filename="test.pdf")
        store.save_meta("test-pg-1", meta)
        loaded = store.load_meta("test-pg-1")
        assert loaded is not None
        assert loaded.doc_id == "test-pg-1"

    def test_save_and_load_json(self, tmp_path):
        store = PgStore(database_url="", local_fallback_dir=str(tmp_path))
        store.ensure_layout("test-pg-2")
        store.save_json("test-pg-2", "extracted/data.json", {"key": "value"})
        data = store.load_json("test-pg-2", "extracted/data.json")
        assert data == {"key": "value"}

    def test_load_missing_returns_none(self, tmp_path):
        store = PgStore(database_url="", local_fallback_dir=str(tmp_path))
        assert store.load_meta("nonexistent") is None
        assert store.load_json("nonexistent", "x.json") is None

    def test_save_markdown(self, tmp_path):
        store = PgStore(database_url="", local_fallback_dir=str(tmp_path))
        store.ensure_layout("test-pg-3")
        path = store.save_markdown("test-pg-3", "report/test.md", "# Hello")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "# Hello"

    def test_doc_dir_creates_directory(self, tmp_path):
        store = PgStore(database_url="", local_fallback_dir=str(tmp_path))
        d = store.doc_dir("test-pg-4")
        assert d.exists()

    def test_save_raw_pdf(self, tmp_path):
        store = PgStore(database_url="", local_fallback_dir=str(tmp_path))
        pdf_src = tmp_path / "source.pdf"
        pdf_src.write_bytes(b"%PDF-1.4 test content")
        path = store.save_raw_pdf("test-pg-5", str(pdf_src))
        assert path.exists()
        assert path.read_bytes().startswith(b"%PDF")
