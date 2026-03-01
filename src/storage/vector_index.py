from __future__ import annotations

import heapq
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.schemas.models import Chunk, Table
from src.finance.utils import table_to_text
from src.utils.logging import get_logger

_logger = get_logger(__name__)

try:
    from langchain_core.documents import Document
except Exception:  # pragma: no cover - optional dependency
    @dataclass(slots=True)
    class Document:  # type: ignore[no-redef]
        page_content: str
        metadata: dict[str, Any]

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    TEXT_SPLITTER_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    RecursiveCharacterTextSplitter = None  # type: ignore[assignment,misc]
    TEXT_SPLITTER_AVAILABLE = False

# Optional embedding / FAISS imports
try:
    import faiss  # type: ignore[import-untyped]

    FAISS_AVAILABLE = True
except Exception:  # pragma: no cover
    faiss = None  # type: ignore[assignment]
    FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

    ST_AVAILABLE = True
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore[assignment]
    ST_AVAILABLE = False

# Default embedding models per language family
_DEFAULT_MODELS: dict[str, str] = {
    "zh": "BAAI/bge-base-zh-v1.5",
    "cn": "BAAI/bge-base-zh-v1.5",
    "en": "sentence-transformers/all-MiniLM-L6-v2",
}
_FALLBACK_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Helpers shared by both index types
# ---------------------------------------------------------------------------

def _prepare_documents(
    chunks: list[Chunk],
    tables: list[Table],
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[Document]:
    """Convert Chunk/Table lists into a flat list of LangChain Documents."""
    documents: list[Document] = []

    if TEXT_SPLITTER_AVAILABLE and RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )
    else:
        splitter = None

    for chunk in chunks:
        text_blocks = [chunk.text]
        if splitter is not None:
            text_blocks = splitter.split_text(chunk.text)
        for idx, text in enumerate(text_blocks):
            content = text.strip()
            if not content:
                continue
            documents.append(
                Document(
                    page_content=content,
                    metadata={
                        "source_type": "chunk",
                        "chunk_id": chunk.chunk_id,
                        "split_index": idx,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "section": chunk.section,
                    },
                )
            )

    for table in tables:
        text = table.raw_markdown or table_to_text(table)
        if not text.strip():
            continue
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source_type": "table",
                    "table_id": table.table_id,
                    "page": table.page,
                    "title": table.title,
                },
            )
        )

    return documents


# ---------------------------------------------------------------------------
# LocalVectorIndex  (token-overlap, deterministic, no deps)
# ---------------------------------------------------------------------------


class LocalVectorIndex:
    """A lightweight local retriever for RAG-style context assembly.

    The index stores LangChain `Document` objects and ranks by token overlap.
    It is intentionally deterministic and offline-friendly for MVP usage.
    """

    def __init__(self, documents: list[Document]) -> None:
        self._documents = documents

    @classmethod
    def from_chunks_and_tables(
        cls,
        chunks: list[Chunk],
        tables: list[Table],
        *,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> LocalVectorIndex:
        documents = _prepare_documents(chunks, tables, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return cls(documents)

    def search(self, query: str, *, k: int = 6) -> list[Document]:
        tokens = _tokenize(query)
        if not tokens:
            return self._documents[:k]

        scored = [(_score(tokens, doc.page_content), idx, doc) for idx, doc in enumerate(self._documents)]
        top_k = heapq.nlargest(k, scored, key=lambda item: item[0])
        top = [doc for score, _idx, doc in top_k if score > 0]
        if top:
            return top
        return self._documents[:k]

    @property
    def size(self) -> int:
        return len(self._documents)


# ---------------------------------------------------------------------------
# EmbeddingVectorIndex  (FAISS + sentence-transformers)
# ---------------------------------------------------------------------------


class EmbeddingVectorIndex:
    """FAISS-backed vector index with sentence-transformer embeddings.

    Falls back gracefully: if ``faiss`` or ``sentence-transformers`` is not
    installed, :meth:`from_chunks_and_tables` raises ``RuntimeError``.
    """

    def __init__(
        self,
        documents: list[Document],
        embeddings: Any,
        index: Any,
        model: Any,
    ) -> None:
        self._documents = documents
        self._embeddings = embeddings
        self._index = index
        self._model = model

    @classmethod
    def from_chunks_and_tables(
        cls,
        chunks: list[Chunk],
        tables: list[Table],
        *,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        model_name: str | None = None,
        lang: str = "auto",
    ) -> EmbeddingVectorIndex:
        if not FAISS_AVAILABLE or not ST_AVAILABLE:
            raise RuntimeError(
                "faiss-cpu and sentence-transformers are required for EmbeddingVectorIndex. "
                "Install with: pip install faiss-cpu sentence-transformers"
            )
        import numpy as np

        documents = _prepare_documents(chunks, tables, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not documents:
            raise RuntimeError("No documents to index")

        resolved_model = model_name or _resolve_model_name(lang)
        _logger.info("embedding_index_init", extra={"model": resolved_model, "n_docs": len(documents)})

        model = SentenceTransformer(resolved_model)
        texts = [doc.page_content for doc in documents]
        embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        embeddings = np.asarray(embeddings, dtype=np.float32)

        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)  # inner-product on L2-normalised vectors = cosine
        index.add(embeddings)

        return cls(documents, embeddings, index, model)

    def search(self, query: str, *, k: int = 6) -> list[Document]:
        import numpy as np

        q_emb = self._model.encode([query], show_progress_bar=False, normalize_embeddings=True)
        q_emb = np.asarray(q_emb, dtype=np.float32)
        actual_k = min(k, len(self._documents))
        scores, indices = self._index.search(q_emb, actual_k)
        results: list[Document] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            results.append(self._documents[idx])
        return results

    def save(self, path: str) -> None:
        """Persist the FAISS index to *path*."""
        if faiss is None:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, path)

    @property
    def size(self) -> int:
        return len(self._documents)


# ---------------------------------------------------------------------------
# HybridRetriever  (embedding + BM25 token-overlap reranking)
# ---------------------------------------------------------------------------


class HybridRetriever:
    """Combines embedding similarity with BM25-style keyword overlap.

    ``alpha`` controls the weighting: final_score = alpha * embedding + (1 - alpha) * bm25.
    """

    def __init__(
        self,
        embedding_index: EmbeddingVectorIndex,
        token_index: LocalVectorIndex,
        *,
        alpha: float = 0.7,
    ) -> None:
        self._emb = embedding_index
        self._tok = token_index
        self._alpha = alpha

    @classmethod
    def from_chunks_and_tables(
        cls,
        chunks: list[Chunk],
        tables: list[Table],
        *,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        model_name: str | None = None,
        lang: str = "auto",
        alpha: float = 0.7,
    ) -> HybridRetriever:
        emb_index = EmbeddingVectorIndex.from_chunks_and_tables(
            chunks, tables, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            model_name=model_name, lang=lang,
        )
        tok_index = LocalVectorIndex.from_chunks_and_tables(
            chunks, tables, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        )
        return cls(emb_index, tok_index, alpha=alpha)

    def search(self, query: str, *, k: int = 6) -> list[Document]:
        # Fetch more candidates from each index
        candidate_k = min(k * 3, max(self._emb.size, self._tok.size))
        emb_docs = self._emb.search(query, k=candidate_k)
        tok_docs = self._tok.search(query, k=candidate_k)

        # Build score maps keyed by doc object identity
        emb_scores: dict[int, float] = {}
        for rank, doc in enumerate(emb_docs):
            emb_scores[id(doc)] = 1.0 / (rank + 1)

        tok_scores: dict[int, float] = {}
        for rank, doc in enumerate(tok_docs):
            tok_scores[id(doc)] = 1.0 / (rank + 1)

        # Merge all candidate docs
        all_docs: dict[int, Document] = {}
        for doc in emb_docs + tok_docs:
            all_docs[id(doc)] = doc

        # Compute hybrid scores
        scored: list[tuple[float, int, Document]] = []
        for doc_id, doc in all_docs.items():
            e = emb_scores.get(doc_id, 0.0)
            t = tok_scores.get(doc_id, 0.0)
            combined = self._alpha * e + (1 - self._alpha) * t
            scored.append((combined, doc_id, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, _, doc in scored[:k]]

    @property
    def size(self) -> int:
        return self._emb.size


# ---------------------------------------------------------------------------
# Factory: build the best available index
# ---------------------------------------------------------------------------


def build_rag_index(
    chunks: list[Chunk],
    tables: list[Table],
    *,
    lang: str = "auto",
) -> LocalVectorIndex | EmbeddingVectorIndex | HybridRetriever:
    """Return the best available RAG index based on ``RAG_MODE`` env var.

    - ``token_overlap`` (default): deterministic, no extra dependencies.
    - ``embedding``: FAISS + sentence-transformers.
    - ``hybrid``: embedding + token-overlap reranking.
    """
    mode = os.getenv("RAG_MODE", "token_overlap").lower()
    model_name = os.getenv("EMBEDDING_MODEL", "") or None
    if model_name == "auto":
        model_name = None

    if mode in ("embedding", "hybrid"):
        try:
            if mode == "hybrid":
                return HybridRetriever.from_chunks_and_tables(
                    chunks, tables, model_name=model_name, lang=lang,
                )
            return EmbeddingVectorIndex.from_chunks_and_tables(
                chunks, tables, model_name=model_name, lang=lang,
            )
        except (RuntimeError, Exception) as exc:
            _logger.warning("rag_embedding_fallback", extra={"error": str(exc)})

    return LocalVectorIndex.from_chunks_and_tables(chunks, tables)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_model_name(lang: str) -> str:
    return _DEFAULT_MODELS.get(lang, _FALLBACK_MODEL)


def _tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"\W+", text.lower()) if token]


def _score(query_tokens: list[str], content: str) -> float:
    content_tokens = _tokenize(content)
    if not content_tokens:
        return 0.0
    token_set = set(content_tokens)
    overlap = sum(1 for token in query_tokens if token in token_set)
    if overlap == 0:
        return 0.0
    length_penalty = math.log(len(content_tokens) + 1, 10)
    return overlap / max(length_penalty, 1.0)
