from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from src.agent.graph import build_graph, get_cached_state
from src.agent.state import AgentState
from src.api.auth import verify_api_key
from src.schemas.models import DocumentMeta
from src.storage.local_store import LocalStore
from src.storage.task_store import TaskStore
from src.utils.ids import new_doc_id
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)
store = LocalStore()
task_store = TaskStore()

# Honour both the legacy env var and the new explicit one
_MAX_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", os.getenv("MAX_UPLOAD_MB", "100")))
MAX_UPLOAD_BYTES = _MAX_MB * 1024 * 1024

# PDF magic bytes
_PDF_MAGIC = b"%PDF"
# Safe filename pattern
_SAFE_FILENAME_RE = re.compile(r"[^\w.\-]")
_MAX_FILENAME_LEN = 128


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _err(code: str, message: str) -> dict[str, Any]:
    status_map = {"not_found": 404, "bad_request": 400, "unauthorized": 401}
    raise HTTPException(
        status_code=status_map.get(code, 400),
        detail={"ok": False, "data": None, "error": {"code": code, "message": message}},
    )


def _sanitize_filename(name: str) -> str:
    """Strip path components and non-safe chars; enforce max length."""
    name = Path(name).name
    name = _SAFE_FILENAME_RE.sub("_", name)
    if len(name) > _MAX_FILENAME_LEN:
        stem = Path(name).stem[: _MAX_FILENAME_LEN - 4]
        suffix = Path(name).suffix[:4]
        name = stem + suffix
    return name or "uploaded.pdf"


def _validate_pdf_bytes(file: UploadFile, first_bytes: bytes) -> None:
    """Raise HTTPException(400) when the upload is clearly not a PDF."""
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type and "/" in content_type and "pdf" not in content_type and "octet" not in content_type:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": {
                    "code": "bad_request",
                    "message": f"Unsupported file type '{content_type}'. Only PDF files are accepted.",
                },
            },
        )
    if len(first_bytes) < 4 or first_bytes[:4] != _PDF_MAGIC:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": {
                    "code": "bad_request",
                    "message": "File does not appear to be a valid PDF (missing %PDF header).",
                },
            },
        )


_AuthDep = Annotated[None, Depends(verify_api_key)]


@router.post("/documents")
async def create_document(
    _auth: _AuthDep,
    file: UploadFile = File(...),
    company: str | None = Form(default=None),
    period_end: str | None = Form(default=None),
    report_type: str | None = Form(default=None),
    language: str | None = Form(default=None),
):
    doc_id = new_doc_id()
    doc_dir = store.doc_dir(doc_id)
    raw_path = doc_dir / "raw.pdf"
    safe_filename = _sanitize_filename(file.filename or "uploaded.pdf")

    total_size = 0
    header_validated = False
    with raw_path.open("wb") as f:
        while chunk := await file.read(64 * 1024):
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_BYTES:
                raw_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {_MAX_MB}MB limit",
                )
            if not header_validated:
                try:
                    _validate_pdf_bytes(file, chunk[:8])
                except HTTPException:
                    raw_path.unlink(missing_ok=True)
                    raise
                header_validated = True
            f.write(chunk)

    parsed_period = date.fromisoformat(period_end) if period_end else None
    meta = DocumentMeta(
        doc_id=doc_id,
        filename=safe_filename,
        company=company,
        period_end=parsed_period,
        report_type=report_type,
        language=language,
    )
    store.save_meta(doc_id, meta)
    task_store.create(doc_id)
    return _ok({"doc_id": doc_id})


@router.post("/documents/{doc_id}/analyze")
async def analyze_document(
    _auth: _AuthDep,
    doc_id: str,
    background_tasks: BackgroundTasks,
):
    meta = store.load_meta(doc_id)
    if not meta:
        return _err("not_found", "Document not found")
    pdf_path = store.doc_dir(doc_id) / "raw.pdf"
    if not pdf_path.exists():
        return _err("not_found", "PDF not found")

    from src.tasks import is_celery_backend

    if is_celery_backend():
        from src.tasks.analysis import run_analysis

        run_analysis.delay(doc_id, str(pdf_path), meta.model_dump(mode="json"))
    else:
        background_tasks.add_task(_run_analysis, meta, str(pdf_path))
    task_store.update(doc_id, status="running", progress=5)
    return _ok(task_store.get(doc_id))


@router.get("/documents/{doc_id}")
async def get_document(_auth: _AuthDep, doc_id: str):
    meta = store.load_meta(doc_id)
    task = task_store.get(doc_id)
    if not meta or not task:
        return _err("not_found", "Document not found")
    return _ok({"meta": meta.model_dump(), "task": task})


@router.get("/documents/{doc_id}/report")
async def get_report(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "report/trader_report.json")
    if not data:
        return _err("not_found", "Report not found")
    return _ok(data)


@router.get("/documents/{doc_id}/report.md")
async def get_report_md(_auth: _AuthDep, doc_id: str):
    path = Path(store.base_dir) / doc_id / "report" / "trader_report.md"
    if not path.exists():
        return _err("not_found", "Report not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@router.get("/documents/{doc_id}/statements")
async def get_statements(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/statements.json")
    if not data:
        return _err("not_found", "Statements not found")
    return _ok(data)


@router.get("/documents/{doc_id}/notes")
async def get_notes(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/notes.json")
    if not data:
        return _err("not_found", "Notes not found")
    return _ok(data)


@router.get("/documents/{doc_id}/risk-signals")
async def get_risk_signals(_auth: _AuthDep, doc_id: str):
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
        _save_partial_results(meta.doc_id)
        task_store.update(meta.doc_id, status="failed", progress=100, error_message=str(exc))


def _save_partial_results(doc_id: str) -> None:
    """Flush whatever pipeline state was cached to disk on analysis failure."""
    partial = get_cached_state(doc_id)
    if partial is None:
        return
    try:
        s = LocalStore(partial.data_dir or "data")
        if partial.pages:
            s.save_json(doc_id, "extracted/pages.json", [p.model_dump() for p in partial.pages])
        if partial.tables:
            s.save_json(doc_id, "extracted/tables.json", [t.model_dump() for t in partial.tables])
        if partial.statements:
            s.save_json(doc_id, "extracted/statements.json", {k: v.model_dump() for k, v in partial.statements.items()})
        if partial.notes:
            s.save_json(doc_id, "extracted/notes.json", [n.model_dump() for n in partial.notes])
        if partial.risk_signals:
            s.save_json(doc_id, "extracted/risk_signals.json", [sig.model_dump() for sig in partial.risk_signals])
    except Exception:
        pass
