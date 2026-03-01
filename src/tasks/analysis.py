"""Celery tasks for asynchronous document analysis.

The primary task :func:`run_analysis` replaces ``FastAPI.BackgroundTasks``
when ``TASK_BACKEND=celery``.
"""

from __future__ import annotations

import os
from typing import Any

from src.utils.logging import get_logger

_logger = get_logger(__name__)

try:
    from src.tasks import app

    if app is not None:
        @app.task(bind=True, max_retries=2, default_retry_delay=30, name="run_analysis")
        def run_analysis(self: Any, doc_id: str, pdf_path: str, meta_dict: dict[str, Any]) -> dict[str, Any]:
            """Execute the LangGraph analysis pipeline as a Celery task.

            Progress is reported via :class:`~src.storage.task_store.TaskStore`
            updates at each pipeline node.
            """
            from src.agent.graph import build_graph
            from src.agent.state import AgentState
            from src.schemas.models import DocumentMeta
            from src.storage.task_store import TaskStore

            data_dir = os.getenv("DATA_DIR", "data")
            task_store = TaskStore(data_dir)

            meta = DocumentMeta.model_validate(meta_dict)
            task_store.update(doc_id, status="running", progress=10)

            graph = build_graph()
            state = AgentState(doc_meta=meta, pdf_path=pdf_path, data_dir=data_dir)

            try:
                graph.invoke(state.model_dump())
                task_store.update(doc_id, status="succeeded", progress=100)
                return {"doc_id": doc_id, "status": "succeeded"}
            except Exception as exc:
                _logger.error("celery_analysis_failed", extra={"doc_id": doc_id, "error": str(exc)})
                # Persist partial results
                _save_partial(doc_id, data_dir)
                # Retry on transient errors
                try:
                    raise self.retry(exc=exc)
                except self.MaxRetriesExceededError:
                    task_store.update(doc_id, status="failed", progress=100, error_message=str(exc))
                    return {"doc_id": doc_id, "status": "failed", "error": str(exc)}


        def _save_partial(doc_id: str, data_dir: str) -> None:
            """Best-effort partial result persistence on failure."""
            try:
                from src.agent.graph import get_cached_state
                from src.storage.local_store import LocalStore

                partial = get_cached_state(doc_id)
                if partial is None:
                    return
                s = LocalStore(partial.data_dir or data_dir)
                if partial.pages:
                    s.save_json(doc_id, "extracted/pages.json", [p.model_dump() for p in partial.pages])
                if partial.tables:
                    s.save_json(doc_id, "extracted/tables.json", [t.model_dump() for t in partial.tables])
                if partial.statements:
                    s.save_json(doc_id, "extracted/statements.json", {k: v.model_dump() for k, v in partial.statements.items()})
            except Exception:
                pass
    else:
        # Celery not available — provide a no-op stub so imports don't break
        def run_analysis(doc_id: str, pdf_path: str, meta_dict: dict[str, Any]) -> dict[str, Any]:  # type: ignore[misc]
            raise RuntimeError("Celery is not configured. Set TASK_BACKEND=background or install celery[redis].")

except Exception:  # pragma: no cover
    def run_analysis(doc_id: str, pdf_path: str, meta_dict: dict[str, Any]) -> dict[str, Any]:  # type: ignore[misc]
        raise RuntimeError("Celery is not configured. Set TASK_BACKEND=background or install celery[redis].")
