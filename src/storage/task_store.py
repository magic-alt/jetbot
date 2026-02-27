from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any


class TaskStore:
    def __init__(self, base_dir: str = "data") -> None:
        db_path = Path(base_dir) / "tasks.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "  doc_id TEXT PRIMARY KEY,"
            "  status TEXT NOT NULL DEFAULT 'queued',"
            "  progress INTEGER NOT NULL DEFAULT 0,"
            "  error_message TEXT"
            ")"
        )
        self._conn.commit()
        self._lock = Lock()

    def create(self, doc_id: str) -> dict[str, Any]:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO tasks (doc_id, status, progress, error_message) VALUES (?, ?, ?, ?)",
                (doc_id, "queued", 0, None),
            )
            self._conn.commit()
        return {"doc_id": doc_id, "status": "queued", "progress": 0, "error_message": None}

    def update(
        self, doc_id: str, status: str | None = None, progress: int | None = None, error_message: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT doc_id, status, progress, error_message FROM tasks WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            if row is None:
                current = {"doc_id": doc_id, "status": "queued", "progress": 0, "error_message": None}
            else:
                current = {"doc_id": row[0], "status": row[1], "progress": row[2], "error_message": row[3]}
            if status is not None:
                current["status"] = status
            if progress is not None:
                current["progress"] = progress
            if error_message is not None:
                current["error_message"] = error_message
            self._conn.execute(
                "INSERT OR REPLACE INTO tasks (doc_id, status, progress, error_message) VALUES (?, ?, ?, ?)",
                (current["doc_id"], current["status"], current["progress"], current["error_message"]),
            )
            self._conn.commit()
        return current

    def get(self, doc_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT doc_id, status, progress, error_message FROM tasks WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        if row is None:
            return None
        return {"doc_id": row[0], "status": row[1], "progress": row[2], "error_message": row[3]}
