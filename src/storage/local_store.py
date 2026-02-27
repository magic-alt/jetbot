from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.schemas.models import DocumentMeta


_SAFE_DOC_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")


class LocalStore:
    def __init__(self, base_dir: str = "data") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_doc_id(doc_id: str) -> None:
        """Ensure doc_id is safe and cannot cause path traversal."""
        if not doc_id or not _SAFE_DOC_ID.match(doc_id):
            raise ValueError(
                f"Invalid doc_id: {doc_id!r}. "
                "Must contain only alphanumeric characters, hyphens, and underscores."
            )

    def _safe_path(self, path: Path) -> Path:
        """Verify that the resolved path is within base_dir."""
        resolved = path.resolve()
        if not str(resolved).startswith(str(self.base_dir)):
            raise ValueError(f"Path traversal detected: {path}")
        return resolved

    def doc_dir(self, doc_id: str) -> Path:
        self._validate_doc_id(doc_id)
        return self._safe_path(self.base_dir / doc_id)

    def ensure_layout(self, doc_id: str) -> dict[str, Path]:
        root = self.doc_dir(doc_id)
        root.mkdir(parents=True, exist_ok=True)
        paths = {
            "root": root,
            "pages": root / "pages",
            "extracted": root / "extracted",
            "report": root / "report",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    def save_raw_pdf(self, doc_id: str, pdf_path: str) -> Path:
        paths = self.ensure_layout(doc_id)
        raw_path = paths["root"] / "raw.pdf"
        raw_path.write_bytes(Path(pdf_path).read_bytes())
        return raw_path

    def save_meta(self, doc_id: str, meta: DocumentMeta) -> Path:
        paths = self.ensure_layout(doc_id)
        meta_path = paths["root"] / "meta.json"
        meta_path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        return meta_path

    def load_meta(self, doc_id: str) -> DocumentMeta | None:
        self._validate_doc_id(doc_id)
        meta_path = self._safe_path(self.base_dir / doc_id / "meta.json")
        if not meta_path.exists():
            return None
        return DocumentMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))

    def save_json(self, doc_id: str, relative_path: str, data: Any) -> Path:
        paths = self.ensure_layout(doc_id)
        full_path = paths["root"] / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return full_path

    def load_json(self, doc_id: str, relative_path: str) -> Any:
        self._validate_doc_id(doc_id)
        full_path = self._safe_path(self.base_dir / doc_id / relative_path)
        if not full_path.exists():
            return None
        return json.loads(full_path.read_text(encoding="utf-8"))

    def save_markdown(self, doc_id: str, relative_path: str, text: str) -> Path:
        self._validate_doc_id(doc_id)
        full_path = self._safe_path(self.base_dir / doc_id / relative_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(text, encoding="utf-8")
        return full_path
