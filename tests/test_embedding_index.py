"""Tests for embedding vector index and RAG factory (src/storage/vector_index.py)."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from src.schemas.models import Chunk, SourceRef, Table
from src.storage.vector_index import (
    LocalVectorIndex,
    EmbeddingVectorIndex,
    HybridRetriever,
    build_rag_index,
    _prepare_documents,
    _resolve_model_name,
    FAISS_AVAILABLE,
    ST_AVAILABLE,
)


def _make_chunks(n: int = 3) -> list[Chunk]:
    texts = [
        "Revenue increased by 20% year over year driven by strong domestic demand.",
        "Total assets reached RMB 5 billion with working capital improving.",
        "Operating cash flow was negative due to large capital expenditure.",
    ]
    return [
        Chunk(
            chunk_id=f"c{i}",
            page_start=i,
            page_end=i,
            section=None,
            text=texts[i % len(texts)],
            bbox=None,
            source_refs=[SourceRef(ref_type="page_text", page=i, table_id=None, quote="test", confidence=0.5)],
        )
        for i in range(n)
    ]


def _make_tables() -> list[Table]:
    return [
        Table(
            table_id="t1",
            page=1,
            title="Balance Sheet",
            cells=[],
            n_rows=2,
            n_cols=3,
            raw_markdown="| Item | Current | Prior |\n| Assets | 100 | 90 |",
            source_refs=[],
        )
    ]


class TestPrepareDocuments:
    def test_returns_documents_from_chunks_and_tables(self):
        docs = _prepare_documents(_make_chunks(), _make_tables())
        assert len(docs) >= 4  # 3 chunks + 1 table

    def test_empty_input_returns_empty(self):
        assert _prepare_documents([], []) == []


class TestLocalVectorIndex:
    def test_search_returns_results(self):
        idx = LocalVectorIndex.from_chunks_and_tables(_make_chunks(), _make_tables())
        results = idx.search("revenue growth", k=2)
        assert len(results) > 0
        assert len(results) <= 2

    def test_size_property(self):
        idx = LocalVectorIndex.from_chunks_and_tables(_make_chunks(), _make_tables())
        assert idx.size >= 3

    def test_empty_query_returns_first_k(self):
        idx = LocalVectorIndex.from_chunks_and_tables(_make_chunks(), _make_tables())
        results = idx.search("", k=2)
        assert len(results) == 2


class TestEmbeddingVectorIndex:
    def test_raises_when_deps_missing(self, monkeypatch):
        monkeypatch.setattr("src.storage.vector_index.FAISS_AVAILABLE", False)
        with pytest.raises(RuntimeError, match="faiss-cpu"):
            EmbeddingVectorIndex.from_chunks_and_tables(_make_chunks(), _make_tables())

    def test_raises_on_empty_docs(self, monkeypatch):
        if not FAISS_AVAILABLE or not ST_AVAILABLE:
            pytest.skip("faiss/sentence-transformers not installed")
        with pytest.raises(RuntimeError, match="No documents"):
            EmbeddingVectorIndex.from_chunks_and_tables([], [])


class TestBuildRagIndex:
    def test_default_returns_local(self, monkeypatch):
        monkeypatch.delenv("RAG_MODE", raising=False)
        idx = build_rag_index(_make_chunks(), _make_tables())
        assert isinstance(idx, LocalVectorIndex)

    def test_token_overlap_explicit(self, monkeypatch):
        monkeypatch.setenv("RAG_MODE", "token_overlap")
        idx = build_rag_index(_make_chunks(), _make_tables())
        assert isinstance(idx, LocalVectorIndex)

    def test_embedding_mode_falls_back_when_deps_missing(self, monkeypatch):
        monkeypatch.setenv("RAG_MODE", "embedding")
        monkeypatch.setattr("src.storage.vector_index.FAISS_AVAILABLE", False)
        idx = build_rag_index(_make_chunks(), _make_tables())
        assert isinstance(idx, LocalVectorIndex)

    def test_hybrid_mode_falls_back_when_deps_missing(self, monkeypatch):
        monkeypatch.setenv("RAG_MODE", "hybrid")
        monkeypatch.setattr("src.storage.vector_index.FAISS_AVAILABLE", False)
        idx = build_rag_index(_make_chunks(), _make_tables())
        assert isinstance(idx, LocalVectorIndex)


class TestResolveModelName:
    def test_zh_returns_bge(self):
        assert "bge" in _resolve_model_name("zh")

    def test_en_returns_minilm(self):
        assert "MiniLM" in _resolve_model_name("en")

    def test_unknown_returns_fallback(self):
        result = _resolve_model_name("kr")
        assert "MiniLM" in result
