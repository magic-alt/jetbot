from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from src.schemas.models import Chunk, Table

try:
    from langchain_core.documents import Document
except Exception:  # pragma: no cover - optional dependency
    @dataclass(slots=True)
    class Document:
        page_content: str
        metadata: dict[str, Any]

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    TEXT_SPLITTER_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    RecursiveCharacterTextSplitter = None  # type: ignore[assignment]
    TEXT_SPLITTER_AVAILABLE = False


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
            text = table.raw_markdown or _table_to_text(table)
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

        return cls(documents)

    def search(self, query: str, *, k: int = 6) -> list[Document]:
        tokens = _tokenize(query)
        if not tokens:
            return self._documents[:k]

        scored: list[tuple[float, Document]] = []
        for doc in self._documents:
            score = _score(tokens, doc.page_content)
            scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        top = [doc for score, doc in scored if score > 0][:k]
        if top:
            return top
        return self._documents[:k]

    @property
    def size(self) -> int:
        return len(self._documents)


def _table_to_text(table: Table) -> str:
    rows: dict[int, list[str]] = {}
    for cell in table.cells:
        rows.setdefault(cell.row, [])
        while len(rows[cell.row]) <= cell.col:
            rows[cell.row].append("")
        rows[cell.row][cell.col] = cell.text
    ordered_rows = [" | ".join(rows[idx]) for idx in sorted(rows)]
    return "\n".join(ordered_rows)


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
