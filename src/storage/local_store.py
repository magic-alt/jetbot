from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.schemas.models import DocumentMeta


class LocalStore:
    def __init__(self, base_dir: str = "data") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def doc_dir(self, doc_id: str) -> Path:
        path = self.base_dir / doc_id
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
        meta_path = self.base_dir / doc_id / "meta.json"
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
        full_path = self.base_dir / doc_id / relative_path
        if not full_path.exists():
            return None
        return json.loads(full_path.read_text(encoding="utf-8"))

    def save_markdown(self, doc_id: str, relative_path: str, text: str) -> Path:
        full_path = self.base_dir / doc_id / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(text, encoding="utf-8")
        return full_path
