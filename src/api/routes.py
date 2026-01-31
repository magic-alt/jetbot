from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import PlainTextResponse

from src.agent.graph import build_graph
from src.agent.state import AgentState
from src.schemas.models import DocumentMeta
from src.storage.local_store import LocalStore
from src.storage.task_store import TaskStore
from src.utils.ids import new_doc_id
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)
store = LocalStore()

task_store = TaskStore()


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


@router.post("/documents")
async def create_document(
    file: UploadFile = File(...),
    company: str | None = Form(default=None),
    period_end: str | None = Form(default=None),
    report_type: str | None = Form(default=None),
    language: str | None = Form(default=None),
):
    doc_id = new_doc_id()
    pdf_bytes = await file.read()
    doc_dir = store.doc_dir(doc_id)
    raw_path = doc_dir / "raw.pdf"
    raw_path.write_bytes(pdf_bytes)

    parsed_period = date.fromisoformat(period_end) if period_end else None
    meta = DocumentMeta(
        doc_id=doc_id,
        filename=file.filename or "uploaded.pdf",
        company=company,
        period_end=parsed_period,
        report_type=report_type,
        language=language,
    )
    store.save_meta(doc_id, meta)
    task_store.create(doc_id)
    return _ok({"doc_id": doc_id})


@router.post("/documents/{doc_id}/analyze")
async def analyze_document(doc_id: str, background_tasks: BackgroundTasks):
    meta = store.load_meta(doc_id)
    if not meta:
        return _err("not_found", "Document not found")
    pdf_path = store.doc_dir(doc_id) / "raw.pdf"
    if not pdf_path.exists():
        return _err("not_found", "PDF not found")

    background_tasks.add_task(_run_analysis, meta, str(pdf_path))
    task_store.update(doc_id, status="running", progress=5)
    return _ok(task_store.get(doc_id))


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    meta = store.load_meta(doc_id)
    task = task_store.get(doc_id)
    if not meta or not task:
        return _err("not_found", "Document not found")
    return _ok({"meta": meta.model_dump(), "task": task})


@router.get("/documents/{doc_id}/report")
async def get_report(doc_id: str):
    data = store.load_json(doc_id, "report/trader_report.json")
    if not data:
        return _err("not_found", "Report not found")
    return _ok(data)


@router.get("/documents/{doc_id}/report.md")
async def get_report_md(doc_id: str):
    path = Path(store.base_dir) / doc_id / "report" / "trader_report.md"
    if not path.exists():
        return _err("not_found", "Report not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@router.get("/documents/{doc_id}/statements")
async def get_statements(doc_id: str):
    data = store.load_json(doc_id, "extracted/statements.json")
    if not data:
        return _err("not_found", "Statements not found")
    return _ok(data)


@router.get("/documents/{doc_id}/notes")
async def get_notes(doc_id: str):
    data = store.load_json(doc_id, "extracted/notes.json")
    if not data:
        return _err("not_found", "Notes not found")
    return _ok(data)


@router.get("/documents/{doc_id}/risk-signals")
async def get_risk_signals(doc_id: str):
    data = store.load_json(doc_id, "extracted/risk_signals.json")
    if not data:
        return _err("not_found", "Risk signals not found")
    return _ok(data)


def _run_analysis(meta: DocumentMeta, pdf_path: str) -> None:
    task_store.update(meta.doc_id, status="running", progress=10)
    graph = build_graph()
    state = AgentState(doc_meta=meta, pdf_path=pdf_path, data_dir=str(store.base_dir))
    try:
        graph.invoke(state.model_dump())
        task_store.update(meta.doc_id, status="succeeded", progress=100)
    except Exception as exc:
        task_store.update(meta.doc_id, status="failed", progress=100, error_message=str(exc))
