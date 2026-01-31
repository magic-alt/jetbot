from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


class TaskStore:
    def __init__(self, base_dir: str = "data") -> None:
        self._path = Path(base_dir) / "tasks.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self._path.exists():
            self._path.write_text("{}", encoding="utf-8")

    def _read(self) -> dict[str, Any]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create(self, doc_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            data[doc_id] = {"doc_id": doc_id, "status": "queued", "progress": 0, "error_message": None}
            self._write(data)
            return data[doc_id]

    def update(self, doc_id: str, status: str | None = None, progress: int | None = None, error_message: str | None = None) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            task = data.get(doc_id, {"doc_id": doc_id})
            if status is not None:
                task["status"] = status
            if progress is not None:
                task["progress"] = progress
            if error_message is not None:
                task["error_message"] = error_message
            data[doc_id] = task
            self._write(data)
            return task

    def get(self, doc_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            return data.get(doc_id)
