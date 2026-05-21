"""PostgreSQL storage backend implementing :class:`StorageBackend`.

Requires ``pip install sqlalchemy[asyncio] asyncpg alembic``.

When ``DATABASE_URL`` is not configured, all operations fall back to the
local filesystem via *local_fallback_dir*.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.schemas.models import DocumentMeta
from src.utils.logging import get_logger

_logger = get_logger(__name__)

try:
    from sqlalchemy import Column, String, Text, create_engine
    from sqlalchemy.orm import Session, declarative_base, sessionmaker

    SA_AVAILABLE = True
except Exception:  # pragma: no cover
    SA_AVAILABLE = False
    create_engine = None  # type: ignore[assignment,misc]
    Session = None  # type: ignore[assignment,misc]
    declarative_base = None  # type: ignore[assignment,misc]

if SA_AVAILABLE and declarative_base is not None:
    Base = declarative_base()

    class DocumentRecord(Base):  # type: ignore[valid-type,misc]
        __tablename__ = "documents"
        doc_id = Column(String(64), primary_key=True, nullable=False)
        meta_json = Column(Text, nullable=True)

    class ArtifactRecord(Base):  # type: ignore[valid-type,misc]
        __tablename__ = "artifacts"
        doc_id = Column(String(64), primary_key=True, nullable=False)
        relative_path = Column(String(256), primary_key=True, nullable=False)
        content = Column(Text, nullable=True)
else:
    Base = None  # type: ignore[assignment,misc]
    DocumentRecord = None  # type: ignore[assignment,misc]
    ArtifactRecord = None  # type: ignore[assignment,misc]


def _sqlalchemy_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


class PgStore:
    """PostgreSQL-backed document store.

    Falls back to local filesystem for binary files (PDFs, images) since
    large blobs are better handled by an object store (see
    :mod:`src.storage.object_store`).
    """

    def __init__(self, database_url: str, local_fallback_dir: str = "data") -> None:
        self._local_dir = Path(local_fallback_dir).resolve()
        self._local_dir.mkdir(parents=True, exist_ok=True)
        self._session_factory = None

        if SA_AVAILABLE and database_url:
            try:
                engine = create_engine(_sqlalchemy_database_url(database_url), pool_pre_ping=True)
                if Base is not None:
                    Base.metadata.create_all(engine)
                self._session_factory = sessionmaker(bind=engine)
                _logger.info("pg_store_connected", extra={"url": database_url[:30] + "..."})
            except Exception as exc:
                _logger.warning("pg_store_fallback_local", extra={"error": str(exc)})

    def _session(self) -> Session | None:
        if self._session_factory is not None:
            return self._session_factory()
        return None

    # -- Directory helpers (local filesystem) --------------------------------

    def doc_dir(self, doc_id: str) -> Path:
        path = self._local_dir / doc_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_layout(self, doc_id: str) -> dict[str, Path]:
        root = self.doc_dir(doc_id)
        paths = {
            "root": root,
            "pages": root / "pages",
            "extracted": root / "extracted",
            "report": root / "report",
        }
        for p in paths.values():
            p.mkdir(parents=True, exist_ok=True)
        return paths

    # -- Binary files (always local) -----------------------------------------

    def save_raw_pdf(self, doc_id: str, pdf_path: str) -> Path:
        paths = self.ensure_layout(doc_id)
        raw_path = paths["root"] / "raw.pdf"
        raw_path.write_bytes(Path(pdf_path).read_bytes())
        return raw_path

    # -- Metadata (Postgres if available, else local JSON) -------------------

    def save_meta(self, doc_id: str, meta: DocumentMeta) -> Path:
        session = self._session()
        if session is not None and DocumentRecord is not None:
            try:
                with session:
                    existing = session.get(DocumentRecord, doc_id)
                    if existing:
                        existing.meta_json = meta.model_dump_json()  # type: ignore[assignment]
                    else:
                        session.add(DocumentRecord(doc_id=doc_id, meta_json=meta.model_dump_json()))
                    session.commit()
            except Exception as exc:
                _logger.warning("pg_save_meta_fallback", extra={"error": str(exc)})

        # Always write locally too (for binary-file co-location)
        paths = self.ensure_layout(doc_id)
        meta_path = paths["root"] / "meta.json"
        meta_path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        return meta_path

    def load_meta(self, doc_id: str) -> DocumentMeta | None:
        session = self._session()
        if session is not None and DocumentRecord is not None:
            try:
                with session:
                    record = session.get(DocumentRecord, doc_id)
                    if record and record.meta_json:
                        return DocumentMeta.model_validate_json(record.meta_json)  # type: ignore[arg-type]
            except Exception:
                pass

        # Fallback: local file
        meta_path = self._local_dir / doc_id / "meta.json"
        if meta_path.exists():
            return DocumentMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
        return None

    def list_metas(self) -> list[DocumentMeta]:
        metas_by_id: dict[str, DocumentMeta] = {}

        session = self._session()
        if session is not None and DocumentRecord is not None:
            try:
                with session:
                    for record in session.query(DocumentRecord).all():
                        if record.meta_json:
                            meta = DocumentMeta.model_validate_json(record.meta_json)  # type: ignore[arg-type]
                            metas_by_id[meta.doc_id] = meta
            except Exception:
                pass

        if self._local_dir.exists():
            for entry in self._local_dir.iterdir():
                if not entry.is_dir() or entry.name in metas_by_id:
                    continue
                meta_path = entry / "meta.json"
                if meta_path.exists():
                    try:
                        meta = DocumentMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    metas_by_id[meta.doc_id] = meta

        return list(metas_by_id.values())

    def delete_document(self, doc_id: str) -> bool:
        found = self.load_meta(doc_id) is not None

        session = self._session()
        if session is not None and DocumentRecord is not None and ArtifactRecord is not None:
            try:
                with session:
                    session.query(ArtifactRecord).filter_by(doc_id=doc_id).delete()
                    record = session.get(DocumentRecord, doc_id)
                    if record is not None:
                        session.delete(record)
                        found = True
                    session.commit()
            except Exception as exc:
                _logger.warning("pg_delete_document_failed", extra={"doc_id": doc_id, "error": str(exc)})

        doc_dir = self._local_dir / doc_id
        if doc_dir.exists():
            shutil.rmtree(doc_dir)
            found = True
        return found

    # -- JSON artifacts (Postgres if available, else local) ------------------

    def save_json(self, doc_id: str, relative_path: str, data: Any) -> Path:
        json_str = json.dumps(data, ensure_ascii=False, indent=2)

        session = self._session()
        if session is not None and ArtifactRecord is not None:
            try:
                with session:
                    existing = session.get(ArtifactRecord, (doc_id, relative_path))
                    if existing:
                        existing.content = json_str  # type: ignore[assignment]
                    else:
                        session.add(ArtifactRecord(doc_id=doc_id, relative_path=relative_path, content=json_str))
                    session.commit()
            except Exception as exc:
                _logger.warning("pg_save_json_fallback", extra={"error": str(exc)})

        # Always write locally
        paths = self.ensure_layout(doc_id)
        full_path = paths["root"] / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(json_str, encoding="utf-8")
        return full_path

    def load_json(self, doc_id: str, relative_path: str) -> Any:
        session = self._session()
        if session is not None and ArtifactRecord is not None:
            try:
                with session:
                    record = session.get(ArtifactRecord, (doc_id, relative_path))
                    if record and record.content:
                        return json.loads(record.content)  # type: ignore[arg-type]
            except Exception:
                pass

        full_path = self._local_dir / doc_id / relative_path
        if full_path.exists():
            return json.loads(full_path.read_text(encoding="utf-8"))
        return None

    # -- Markdown artifacts --------------------------------------------------

    def save_markdown(self, doc_id: str, relative_path: str, text: str) -> Path:
        # Store as artifact in PG too
        session = self._session()
        if session is not None and ArtifactRecord is not None:
            try:
                with session:
                    existing = session.get(ArtifactRecord, (doc_id, relative_path))
                    if existing:
                        existing.content = text  # type: ignore[assignment]
                    else:
                        session.add(ArtifactRecord(doc_id=doc_id, relative_path=relative_path, content=text))
                    session.commit()
            except Exception:
                pass

        paths = self.ensure_layout(doc_id)
        full_path = paths["root"] / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(text, encoding="utf-8")
        return full_path

    def load_markdown(self, doc_id: str, relative_path: str) -> str | None:
        session = self._session()
        if session is not None and ArtifactRecord is not None:
            try:
                with session:
                    record = session.get(ArtifactRecord, (doc_id, relative_path))
                    if record and record.content is not None:
                        return str(record.content)
            except Exception:
                pass

        full_path = self._local_dir / doc_id / relative_path
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return None
