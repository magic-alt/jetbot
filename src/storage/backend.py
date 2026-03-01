"""Storage backend Protocol — abstracts the document store interface.

Both :class:`~src.storage.local_store.LocalStore` and
:class:`~src.storage.pg_store.PgStore` implement this protocol so that
the caller can switch backends via ``STORAGE_BACKEND`` env var.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.schemas.models import DocumentMeta


@runtime_checkable
class StorageBackend(Protocol):
    """Minimal interface every document store must satisfy."""

    def doc_dir(self, doc_id: str) -> Path:
        """Return the root directory (or logical path) for a document."""
        ...

    def ensure_layout(self, doc_id: str) -> dict[str, Path]:
        """Create the directory structure for *doc_id* and return path map."""
        ...

    def save_raw_pdf(self, doc_id: str, pdf_path: str) -> Path:
        ...

    def save_meta(self, doc_id: str, meta: DocumentMeta) -> Path:
        ...

    def load_meta(self, doc_id: str) -> DocumentMeta | None:
        ...

    def save_json(self, doc_id: str, relative_path: str, data: Any) -> Path:
        ...

    def load_json(self, doc_id: str, relative_path: str) -> Any:
        ...

    def save_markdown(self, doc_id: str, relative_path: str, text: str) -> Path:
        ...


def get_storage_backend(base_dir: str | None = None) -> StorageBackend:
    """Return the storage backend based on ``STORAGE_BACKEND`` env var.

    - ``local`` (default): :class:`~src.storage.local_store.LocalStore`
    - ``postgres``: :class:`~src.storage.pg_store.PgStore`
    """
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    data_dir = base_dir or os.getenv("DATA_DIR") or "data"

    if backend == "postgres":
        from src.storage.pg_store import PgStore

        return PgStore(database_url=os.getenv("DATABASE_URL", ""), local_fallback_dir=data_dir)

    from src.storage.local_store import LocalStore

    return LocalStore(data_dir)
