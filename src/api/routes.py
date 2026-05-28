from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from src.agent.capabilities import get_agent_capabilities
from src.agent.graph import build_graph, get_cached_state
from src.agent.state import AgentState
from src.api.auth import verify_api_key
from src.finance.facts import apply_corrections
from src.pdf.engine import get_pdf_engine
from src.pdf.operations import (
    delete_pages,
    extract_pages,
    page_count as pdf_page_count,
    reorder_pages,
    rotate_pages,
)
from src.schemas.models import Correction, DocumentMeta, FinancialFact, SourceRef
from src.storage.backend import get_storage_backend
from src.storage.task_store import TaskStore
from src.utils.document_metadata import enrich_document_meta
from src.utils.ids import new_doc_id
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)
DATA_DIR = os.getenv("DATA_DIR") or "data"
store = get_storage_backend(DATA_DIR)
task_store = TaskStore(DATA_DIR)

# Honour both the legacy env var and the new explicit one
_MAX_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", os.getenv("MAX_UPLOAD_MB", "100")))
MAX_UPLOAD_BYTES = _MAX_MB * 1024 * 1024

# PDF magic bytes
_PDF_MAGIC = b"%PDF"
# Safe filename pattern
_SAFE_FILENAME_RE = re.compile(r"[^\w.\-]")
_MAX_FILENAME_LEN = 128
_SAFE_REVISION_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
_CORRECTABLE_FACT_FIELDS = {
    "value",
    "concept",
    "label",
    "raw_label",
    "unit",
    "currency",
    "scale",
    "period_start",
    "period_end",
    "period_type",
    "source_refs",
}
_CORRECTION_FIELD_ALIASES = {"evidence": "source_refs"}


class PdfOperationRequest(BaseModel):
    operation: Literal["extract", "delete", "reorder", "rotate"]
    pages: list[int] | None = Field(default=None)
    degrees: int = Field(default=90)


class CorrectionCreateRequest(BaseModel):
    field_name: str
    new_value: Any = None
    old_value: Any = None
    actor: str = "analyst"
    reason: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


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


def _validate_revision_id(revision_id: str) -> None:
    if not revision_id or not _SAFE_REVISION_RE.match(revision_id):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": {
                    "code": "bad_request",
                    "message": "Invalid revision_id.",
                },
            },
        )


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


def _load_enriched_meta(doc_id: str) -> DocumentMeta | None:
    meta = store.load_meta(doc_id)
    if meta is None:
        return None
    pages = store.load_json(doc_id, "extracted/pages.json") or []
    enriched = enrich_document_meta(meta, pages)
    if enriched != meta:
        store.save_meta(doc_id, enriched)
    return enriched


def _require_document(doc_id: str) -> DocumentMeta:
    meta = store.load_meta(doc_id)
    if meta is None:
        _err("not_found", "Document not found")
        raise AssertionError("unreachable")
    return meta


def _load_fact_models(doc_id: str) -> list[FinancialFact]:
    data = store.load_json(doc_id, "extracted/facts.json")
    if data is None:
        _err("not_found", "Facts not found")
    return [FinancialFact.model_validate(item) for item in data]


def _load_correction_models(doc_id: str) -> list[Correction]:
    data = store.load_json(doc_id, "extracted/corrections.json")
    if data is None:
        return []
    return [Correction.model_validate(item) for item in data]


def _save_correction_models(doc_id: str, corrections: list[Correction]) -> None:
    store.save_json(
        doc_id,
        "extracted/corrections.json",
        [correction.model_dump(mode="json") for correction in corrections],
    )


def _save_effective_facts(doc_id: str, facts: list[FinancialFact], corrections: list[Correction]) -> list[FinancialFact]:
    effective_facts = apply_corrections(facts, corrections)
    store.save_json(
        doc_id,
        "extracted/effective_facts.json",
        [fact.model_dump(mode="json") for fact in effective_facts],
    )
    return effective_facts


def _normalize_correction_field(field_name: str) -> str:
    return _CORRECTION_FIELD_ALIASES.get(field_name, field_name)


def _validated_corrected_fact(fact: FinancialFact, field_name: str, new_value: Any) -> FinancialFact:
    updated_payload = fact.model_dump(mode="python")
    updated_payload[field_name] = new_value
    try:
        return FinancialFact.model_validate(updated_payload)
    except ValidationError as exc:
        _err("bad_request", f"Invalid value for correction field '{field_name}': {exc.errors()[0]['msg']}")
        raise AssertionError("unreachable")


_AuthDep = Annotated[None, Depends(verify_api_key)]


@router.post("/documents")
async def create_document(
    _auth: _AuthDep,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    company: str | None = Form(default=None),
    ticker: str | None = Form(default=None),
    cik: str | None = Form(default=None),
    filing_type: str | None = Form(default=None),
    period_end: str | None = Form(default=None),
    report_type: str | None = Form(default=None),
    language: str | None = Form(default=None),
):
    doc_id = new_doc_id()
    paths = store.ensure_layout(doc_id)
    raw_path = paths["root"] / "raw.pdf"
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
        ticker=ticker,
        cik=cik,
        filing_type=filing_type,
        period_end=parsed_period,
        report_type=report_type,
        language=language,
    )
    store.save_meta(doc_id, meta)
    task_store.create(doc_id)
    return _ok(_start_analysis(meta, raw_path, background_tasks))


@router.get("/agent/capabilities")
async def list_agent_capabilities(_auth: _AuthDep):
    return _ok([capability.model_dump() for capability in get_agent_capabilities()])


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

    return _ok(_start_analysis(meta, pdf_path, background_tasks))


def _start_analysis(meta: DocumentMeta, pdf_path: Path, background_tasks: BackgroundTasks) -> dict[str, Any]:
    current = task_store.get(meta.doc_id)
    if current is None:
        current = task_store.create(meta.doc_id)
    elif current["status"] == "running":
        return current

    from src.tasks import is_celery_backend

    try:
        if is_celery_backend():
            from src.tasks.analysis import run_analysis

            run_analysis.delay(meta.doc_id, str(pdf_path), meta.model_dump(mode="json"))
        else:
            background_tasks.add_task(_run_analysis, meta, str(pdf_path))
    except Exception as exc:
        task_store.update(meta.doc_id, status="failed", progress=100, current_node=None, error_message=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "data": None,
                "error": {"code": "analysis_start_failed", "message": f"Unable to start analysis: {exc}"},
            },
        ) from exc
    return task_store.update(meta.doc_id, status="running", progress=5, current_node=None, error_message=None)


@router.get("/documents/{doc_id}")
async def get_document(_auth: _AuthDep, doc_id: str):
    meta = _load_enriched_meta(doc_id)
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
    text = store.load_markdown(doc_id, "report/trader_report.md")
    if text is None:
        return _err("not_found", "Report not found")
    return PlainTextResponse(text)


@router.get("/documents/{doc_id}/statements")
async def get_statements(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/statements.json")
    if data is None:
        return _err("not_found", "Statements not found")
    return _ok(data)


@router.get("/documents/{doc_id}/facts")
async def get_facts(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/facts.json")
    if data is None:
        return _err("not_found", "Facts not found")
    return _ok(data)


@router.get("/documents/{doc_id}/facts/effective")
async def get_effective_facts(_auth: _AuthDep, doc_id: str):
    _require_document(doc_id)
    facts = _load_fact_models(doc_id)
    corrections = _load_correction_models(doc_id)
    effective_facts = _save_effective_facts(doc_id, facts, corrections)
    return _ok([fact.model_dump(mode="json") for fact in effective_facts])


@router.get("/documents/{doc_id}/corrections")
async def get_corrections(_auth: _AuthDep, doc_id: str):
    _require_document(doc_id)
    corrections = _load_correction_models(doc_id)
    return _ok([correction.model_dump(mode="json") for correction in corrections])


@router.post("/documents/{doc_id}/facts/{fact_id}/corrections")
async def create_fact_correction(
    _auth: _AuthDep,
    doc_id: str,
    fact_id: str,
    payload: CorrectionCreateRequest,
):
    _require_document(doc_id)
    facts = _load_fact_models(doc_id)
    corrections = _load_correction_models(doc_id)
    effective_facts = apply_corrections(facts, corrections)
    fact = next((item for item in effective_facts if item.fact_id == fact_id), None)
    if fact is None:
        return _err("not_found", "Fact not found")

    field_name = _normalize_correction_field(payload.field_name)
    if field_name not in _CORRECTABLE_FACT_FIELDS:
        return _err("bad_request", f"Unsupported correction field '{payload.field_name}'")
    _validated_corrected_fact(fact, field_name, payload.new_value)

    correction = Correction(
        correction_id=new_doc_id(),
        doc_id=doc_id,
        fact_id=fact_id,
        field_name=field_name,
        old_value=payload.old_value if payload.old_value is not None else getattr(fact, field_name, None),
        new_value=payload.new_value,
        actor=payload.actor,
        reason=payload.reason,
        source_refs=payload.source_refs,
    )
    next_corrections = corrections + [correction]
    _save_correction_models(doc_id, next_corrections)
    next_effective_facts = _save_effective_facts(doc_id, facts, next_corrections)
    next_fact = next((item for item in next_effective_facts if item.fact_id == fact_id), None)
    return _ok(
        {
            "correction": correction.model_dump(mode="json"),
            "effective_fact": next_fact.model_dump(mode="json") if next_fact else None,
            "correction_count": len(next_corrections),
        }
    )


@router.get("/documents/{doc_id}/fact-validation")
async def get_fact_validation(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/fact_validation.json")
    if data is None:
        return _err("not_found", "Fact validation not found")
    return _ok(data)


@router.get("/documents/{doc_id}/notes")
async def get_notes(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/notes.json")
    if data is None:
        return _err("not_found", "Notes not found")
    return _ok(data)


@router.get("/documents/{doc_id}/risk-signals")
async def get_risk_signals(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/risk_signals.json")
    if data is None:
        return _err("not_found", "Risk signals not found")
    return _ok(data)


@router.get("/documents/{doc_id}/deep-analysis")
async def get_deep_analysis(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/deep_analysis.json")
    if data is None:
        return _err("not_found", "Deep analysis not found")
    return _ok(data)


@router.get("/documents/{doc_id}/agent-runs")
async def get_agent_runs(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/agent_runs.json")
    if data is None:
        return _err("not_found", "Agent runs not found")
    return _ok(data)


# ── Web-UI support endpoints ────────────────────────────────────────────────
@router.get("/documents")
async def list_documents(
    _auth: _AuthDep,
    limit: int = 50,
    offset: int = 0,
):
    """Paginated list of documents in the local store, newest first."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    items: list[dict[str, Any]] = []
    for meta in store.list_metas():
        meta = _load_enriched_meta(meta.doc_id) or meta
        task = task_store.get(meta.doc_id)
        items.append(
            {
                "meta": meta.model_dump(mode="json"),
                "task": task,
            }
        )

    items.sort(
        key=lambda it: (it["meta"].get("created_at") or ""),
        reverse=True,
    )
    total = len(items)
    page = items[offset : offset + limit]
    return _ok({"items": page, "total": total, "limit": limit, "offset": offset})


@router.get("/documents/{doc_id}/tables")
async def get_tables(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/tables.json")
    if data is None:
        return _err("not_found", "Tables not found")
    return _ok(data)


@router.delete("/documents/{doc_id}")
async def delete_document(_auth: _AuthDep, doc_id: str):
    meta = store.load_meta(doc_id)
    if meta is None:
        return _err("not_found", "Document not found")
    deleted = store.delete_document(doc_id)
    task_store.delete(doc_id)
    return _ok({"doc_id": doc_id, "deleted": deleted})


@router.get("/documents/{doc_id}/pages")
async def get_pages(_auth: _AuthDep, doc_id: str):
    data = store.load_json(doc_id, "extracted/pages.json")
    if data is None:
        return _err("not_found", "Pages not found")
    return _ok(data)


@router.get("/documents/{doc_id}/pages/{page_number}/image")
async def get_page_image(_auth: _AuthDep, doc_id: str, page_number: int):
    meta = store.load_meta(doc_id)
    if meta is None:
        return _err("not_found", "Document not found")
    if page_number < 1:
        return _err("bad_request", "page_number must be >= 1")
    pdf_path = store.doc_dir(doc_id) / "raw.pdf"
    if not pdf_path.exists():
        return _err("not_found", "PDF not found")
    preview_dir = store.ensure_layout(doc_id)["pages"] / "pdfium_preview"
    try:
        image_path = get_pdf_engine("pdfium").render_page(str(pdf_path), page_number, str(preview_dir), dpi=144)
    except ValueError as exc:
        return _err("bad_request", str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "data": None,
                "error": {"code": "pdfium_unavailable", "message": str(exc)},
            },
        ) from exc
    return FileResponse(image_path, media_type="image/png", headers={"X-PDF-Engine": "pdfium"})


@router.get("/documents/{doc_id}/pdf")
async def get_pdf(_auth: _AuthDep, doc_id: str):
    """Stream the original uploaded PDF for direct links and downloads."""
    meta = store.load_meta(doc_id)
    if meta is None:
        return _err("not_found", "Document not found")
    pdf_path = store.doc_dir(doc_id) / "raw.pdf"
    if not pdf_path.exists():
        return _err("not_found", "PDF not found")
    download_name = meta.filename if meta else "document.pdf"
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        # `inline` so browsers render in the iframe instead of forcing download.
        headers={
            "Content-Disposition": f'inline; filename="{download_name}"',
            # Allow the same-origin SPA to embed this in an <iframe>.
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


@router.post("/documents/{doc_id}/pdf/operations")
async def create_pdf_operation(
    _auth: _AuthDep,
    doc_id: str,
    request: PdfOperationRequest,
):
    """Create a derived PDF from page-level operations without changing raw.pdf."""
    meta = store.load_meta(doc_id)
    if meta is None:
        return _err("not_found", "Document not found")

    source_pdf = store.doc_dir(doc_id) / "raw.pdf"
    if not source_pdf.exists():
        return _err("not_found", "PDF not found")

    revision_id = new_doc_id()
    root = store.doc_dir(doc_id).resolve()
    derived_dir = (root / "derived").resolve()
    if not str(derived_dir).startswith(str(root)):
        return _err("bad_request", "Invalid derived artifact path")
    derived_dir.mkdir(parents=True, exist_ok=True)

    output_pdf = derived_dir / f"{revision_id}.pdf"

    try:
        pages = request.pages
        if request.operation in {"extract", "delete", "reorder"} and not pages:
            return _err("bad_request", f"{request.operation} requires pages")

        if request.operation == "extract":
            extract_pages(str(source_pdf), pages or [], str(output_pdf))
        elif request.operation == "delete":
            delete_pages(str(source_pdf), pages or [], str(output_pdf))
        elif request.operation == "reorder":
            reorder_pages(str(source_pdf), pages or [], str(output_pdf))
        elif request.operation == "rotate":
            rotate_pages(str(source_pdf), pages, str(output_pdf), degrees=request.degrees)
    except ValueError as exc:
        return _err("bad_request", str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "data": None,
                "error": {"code": "pdf_engine_unavailable", "message": str(exc)},
            },
        ) from exc

    manifest = {
        "doc_id": doc_id,
        "revision_id": revision_id,
        "source": "raw.pdf",
        "output_pdf": f"derived/{revision_id}.pdf",
        "operation": request.operation,
        "pages": request.pages,
        "degrees": request.degrees if request.operation == "rotate" else None,
        "page_count": pdf_page_count(str(output_pdf)),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store.save_json(doc_id, f"derived/{revision_id}.json", manifest)

    return _ok(
        {
            **manifest,
            "download_url": f"/v1/documents/{doc_id}/pdf/derived/{revision_id}",
        }
    )


@router.get("/documents/{doc_id}/pdf/derived/{revision_id}")
async def get_derived_pdf(_auth: _AuthDep, doc_id: str, revision_id: str):
    """Stream a derived PDF revision created by a page-level operation."""
    _validate_revision_id(revision_id)
    meta = store.load_meta(doc_id)
    if meta is None:
        return _err("not_found", "Document not found")

    pdf_path = store.doc_dir(doc_id) / "derived" / f"{revision_id}.pdf"
    if not pdf_path.exists():
        return _err("not_found", "Derived PDF not found")

    stem = Path(meta.filename).stem or "document"
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{stem}-{revision_id}.pdf"',
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


def _run_analysis(meta: DocumentMeta, pdf_path: str) -> None:
    task_store.update(meta.doc_id, status="running", progress=10)
    graph = build_graph()
    state = AgentState(doc_meta=meta, pdf_path=pdf_path, data_dir=DATA_DIR)
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
        s = get_storage_backend(partial.data_dir or DATA_DIR)
        if partial.pages:
            s.save_json(doc_id, "extracted/pages.json", [p.model_dump() for p in partial.pages])
        if partial.tables:
            s.save_json(doc_id, "extracted/tables.json", [t.model_dump() for t in partial.tables])
        if partial.statements:
            s.save_json(doc_id, "extracted/statements.json", {k: v.model_dump() for k, v in partial.statements.items()})
        if partial.facts:
            s.save_json(doc_id, "extracted/facts.json", [fact.model_dump(mode="json") for fact in partial.facts])
        if partial.fact_validation_results:
            s.save_json(doc_id, "extracted/fact_validation.json", partial.fact_validation_results.model_dump(mode="json"))
        if partial.notes:
            s.save_json(doc_id, "extracted/notes.json", [n.model_dump() for n in partial.notes])
        if partial.risk_signals:
            s.save_json(doc_id, "extracted/risk_signals.json", [sig.model_dump() for sig in partial.risk_signals])
        if partial.analysis_context:
            s.save_json(doc_id, "extracted/analysis_context.json", partial.analysis_context.model_dump(mode="json"))
        if partial.deep_analysis:
            s.save_json(doc_id, "extracted/deep_analysis.json", partial.deep_analysis.model_dump(mode="json"))
        if partial.agent_runs:
            s.save_json(doc_id, "extracted/agent_runs.json", [run.model_dump(mode="json") for run in partial.agent_runs])
    except Exception:
        pass
