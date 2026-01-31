from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from pydantic import ValidationError

from src.agent.state import AgentState
from src.finance.normalizer import normalize_account_name
from src.finance.signals import generate_signals
from src.finance.validators import validate_statements
from src.llm.base import get_default_llm_client
from src.pdf.extractor import PDFExtractor
from src.pdf.tables import extract_tables as extract_tables_from_pdf
from src.schemas.models import (
    Chunk,
    FinancialStatement,
    KeyNote,
    Page,
    RiskSignal,
    SourceRef,
    StatementLineItem,
    Table,
    TraderReport,
)
from src.storage.local_store import LocalStore
from src.utils.ids import new_doc_id
from src.utils.logging import get_logger, log_node
from src.utils.time import monotonic_ms


logger = get_logger(__name__)


def ingest_pdf(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    data_dir = state.data_dir or "data"
    store = LocalStore(data_dir)

    if "fake_pages" in state.debug:
        fake_pages = state.debug["fake_pages"]
        state.pages = [Page.model_validate(p) if isinstance(p, dict) else p for p in fake_pages]
        state.needs_ocr = False
    else:
        extractor = PDFExtractor()
        render_dir = None
        if os.getenv("DEBUG") == "1":
            render_dir = str(store.ensure_layout(state.doc_meta.doc_id)["pages"])
        try:
            result = extractor.extract(state.pdf_path or "", render_dir=render_dir)
            state.pages = result.pages
            state.needs_ocr = result.needs_ocr
        except Exception as exc:
            state.errors.append(f"ingest_failed:{exc}")
            state.pages = []
            state.needs_ocr = False

    state.debug["page_count"] = len(state.pages)
    if os.getenv("DEBUG") == "1":
        store.save_json(state.doc_meta.doc_id, "extracted/pages.json", [p.model_dump() for p in state.pages])
    log_node(logger, state.doc_meta.doc_id, "ingest_pdf", start_ms)
    return state


def extract_tables(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    if state.pdf_path:
        try:
            state.tables = extract_tables_from_pdf(state.pdf_path)
        except Exception as exc:
            state.errors.append(f"extract_tables_failed:{exc}")
            state.tables = []
    state.debug["table_count"] = len(state.tables)
    log_node(logger, state.doc_meta.doc_id, "extract_tables", start_ms)
    return state


def detect_sections_and_chunk(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    chunks: list[Chunk] = []
    current_text = ""
    current_start = 1
    current_section: str | None = None

    heading_pattern = re.compile(r"^([??????????]+?|\d+\.)")

    for page in state.pages:
        lines = page.text.splitlines()
        for line in lines:
            if heading_pattern.match(line.strip()):
                current_section = line.strip()
        if len(current_text) + len(page.text) > 1200 and current_text:
            chunks.append(
                _build_chunk(current_text, current_start, page.page_number - 1, current_section)
            )
            current_text = ""
            current_start = page.page_number
        current_text += page.text + "\n"

    if current_text.strip():
        chunks.append(_build_chunk(current_text, current_start, state.pages[-1].page_number if state.pages else 1, current_section))

    state.chunks = chunks
    state.debug["chunk_count"] = len(chunks)
    log_node(logger, state.doc_meta.doc_id, "detect_sections_and_chunk", start_ms)
    return state


def extract_financial_statements(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    statements: dict[str, FinancialStatement] = {}
    tables_by_type = {"balance": [], "income": [], "cashflow": []}

    for table in state.tables:
        kind = _detect_statement_type(table)
        if kind:
            tables_by_type[kind].append(table)

    for kind, tables in tables_by_type.items():
        if tables:
            statements[kind] = _tables_to_statement(kind, tables)

    missing = [k for k in ("income", "balance", "cashflow") if k not in statements]
    if missing:
        for kind in missing:
            statements[kind] = _llm_statement(state, kind)

    state.statements = statements
    state.debug["statement_types"] = list(statements.keys())
    log_node(logger, state.doc_meta.doc_id, "extract_financial_statements", start_ms)
    return state


def validate_and_reconcile(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    state.validation_results = validate_statements(state.statements)
    severe = any(
        issue in {"balance_equation_failed", "balance_missing_totals"} or issue.startswith("unit_mismatch")
        for issue in state.validation_results.get("issues", [])
    )
    if severe:
        state.errors.append("validation_failed")
        state.retry_count += 1
    else:
        state.errors = [err for err in state.errors if err != "validation_failed"]
    log_node(logger, state.doc_meta.doc_id, "validate_and_reconcile", start_ms)
    return state


def extract_key_notes(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    system, user = _load_prompt("key_notes_prompt.md"), _build_notes_prompt(state)
    data = _call_llm_json(system, user, schema=_key_notes_schema())
    notes = _validate_notes(data, state)
    if not notes:
        data = _call_llm_json(system, user + "\nRetry with strict JSON.", schema=_key_notes_schema())
        notes = _validate_notes(data, state)
    if not notes:
        notes.append(KeyNote(note_type="other", summary="No notes extracted.", source_refs=_fallback_evidence(state)))
    state.notes = notes
    state.debug["notes_count"] = len(notes)
    log_node(logger, state.doc_meta.doc_id, "extract_key_notes", start_ms)
    return state


def generate_risk_signals(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    pages_text = [page.text for page in state.pages]
    signals = generate_signals(state.statements, state.notes, state.validation_results, pages_text)

    system, user = _load_prompt("trader_report_prompt.md"), _build_signals_prompt(state)
    extra = _call_llm_json(system, user, schema=_risk_signals_schema())
    for raw in extra if isinstance(extra, list) else []:
        try:
            signal = RiskSignal.model_validate(raw)
            if not signal.evidence:
                signal.evidence = _fallback_evidence(state)
            signals.append(signal)
        except ValidationError:
            continue

    state.risk_signals = signals
    state.debug["signals_count"] = len(signals)
    log_node(logger, state.doc_meta.doc_id, "generate_risk_signals", start_ms)
    return state


def build_trader_report(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    system, user = _load_prompt("trader_report_prompt.md"), _build_report_prompt(state)
    data = _call_llm_json(system, user, schema=_trader_report_schema(), validator=TraderReport.model_validate)

    report = TraderReport(
        doc_id=state.doc_meta.doc_id,
        executive_summary=f"Parsed {len(state.pages)} pages for {state.doc_meta.filename}.",
        key_drivers=["See extracted statements and notes."],
        numbers_snapshot=_numbers_snapshot(state),
        risk_signals=state.risk_signals,
        notes=state.notes,
        limitations=[
            "Not financial advice.",
            "Outputs depend on PDF extraction quality.",
        ],
    )

    if isinstance(data, TraderReport):
        report.executive_summary = data.executive_summary
        report.key_drivers = data.key_drivers
        report.numbers_snapshot = data.numbers_snapshot
        report.limitations = list(set(report.limitations + data.limitations))

    state.trader_report = report
    state.debug["report_ready"] = True
    log_node(logger, state.doc_meta.doc_id, "build_trader_report", start_ms)
    return state


def finalize(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    store = LocalStore(state.data_dir or "data")
    store.save_meta(state.doc_meta.doc_id, state.doc_meta)
    store.save_json(state.doc_meta.doc_id, "extracted/pages.json", [p.model_dump() for p in state.pages])
    store.save_json(state.doc_meta.doc_id, "extracted/tables.json", [t.model_dump() for t in state.tables])
    store.save_json(state.doc_meta.doc_id, "extracted/statements.json", {k: v.model_dump() for k, v in state.statements.items()})
    store.save_json(state.doc_meta.doc_id, "extracted/notes.json", [n.model_dump() for n in state.notes])
    store.save_json(state.doc_meta.doc_id, "extracted/risk_signals.json", [s.model_dump() for s in state.risk_signals])
    if state.trader_report:
        store.save_json(state.doc_meta.doc_id, "report/trader_report.json", state.trader_report.model_dump())
        store.save_markdown(state.doc_meta.doc_id, "report/trader_report.md", _render_markdown_report(state))
    log_node(logger, state.doc_meta.doc_id, "finalize", start_ms)
    return state


def _build_chunk(text: str, start: int, end: int, section: str | None) -> Chunk:
    snippet = text.strip().split("\n")[0][:200]
    source = SourceRef(ref_type="page_text", page=start, table_id=None, quote=snippet, confidence=0.4)
    return Chunk(
        chunk_id=new_doc_id(),
        page_start=start,
        page_end=end,
        section=section,
        text=text.strip(),
        bbox=None,
        source_refs=[source],
    )


def _detect_statement_type(table: Table) -> str | None:
    text = " ".join(cell.text for cell in table.cells).lower()
    if "?????" in text or "balance sheet" in text:
        return "balance"
    if "???" in text or "income statement" in text:
        return "income"
    if "?????" in text or "cash flow" in text:
        return "cashflow"
    return None


def _tables_to_statement(kind: str, tables: list[Table]) -> FinancialStatement:
    line_items: list[StatementLineItem] = []
    totals: dict[str, float] = {}
    for table in tables:
        rows = _table_rows(table)
        for row in rows:
            if not row:
                continue
            name_raw = row[0]
            value_current = _parse_number(row[1]) if len(row) > 1 else None
            value_prior = _parse_number(row[2]) if len(row) > 2 else None
            name_norm = normalize_account_name(name_raw)
            item = StatementLineItem(
                name_raw=name_raw,
                name_norm=name_norm,
                value_current=value_current,
                value_prior=value_prior,
                unit=None,
                currency=None,
                notes=None,
                source_refs=table.source_refs,
            )
            line_items.append(item)
            if name_norm in {"total_assets", "total_liabilities", "total_equity", "net_income", "operating_cf", "revenue"} and value_current is not None:
                totals[name_norm] = value_current
    return FinancialStatement(
        statement_type=kind,
        period_end=None,
        period_start=None,
        line_items=line_items,
        totals=totals,
        extraction_confidence=0.6,
        issues=[],
    )


def _table_rows(table: Table) -> list[list[str]]:
    rows: dict[int, list[str]] = {}
    for cell in table.cells:
        rows.setdefault(cell.row, [])
        while len(rows[cell.row]) <= cell.col:
            rows[cell.row].append("")
        rows[cell.row][cell.col] = cell.text
    return [rows[i] for i in sorted(rows.keys())]


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.replace(",", "").strip()
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    try:
        num = float(text)
        return -num if negative else num
    except ValueError:
        return None


def _load_prompt(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _call_llm_json(system: str, user: str, schema: dict[str, Any], validator: Any | None = None) -> Any:
    client = get_default_llm_client()

    async def _call() -> str:
        return await client.chat(system, user, json_schema=schema)

    for attempt in range(2):
        text = asyncio.run(_call())
        try:
            parsed = json.loads(text)
            if validator is None:
                return parsed
            try:
                return validator(parsed)
            except ValidationError:
                if attempt == 1:
                    return parsed
        except json.JSONDecodeError:
            if attempt == 1:
                return {}
    return {}


def _llm_statement(state: AgentState, kind: str) -> FinancialStatement:
    system, user = _load_prompt("statement_extraction_prompt.md"), _build_statement_prompt(state, kind)
    data = _call_llm_json(system, user, schema=_statement_schema(), validator=FinancialStatement.model_validate)
    if isinstance(data, FinancialStatement):
        statement = data
    else:
        statement = FinancialStatement(
            statement_type=kind,
            period_end=None,
            period_start=None,
            line_items=[],
            totals={},
            extraction_confidence=0.2,
            issues=["llm_parse_failed"],
        )
    if not statement.line_items:
        statement.issues.append("no_line_items")
        statement.line_items.append(
            StatementLineItem(
                name_raw="unknown",
                name_norm="unknown",
                value_current=None,
                value_prior=None,
                unit=None,
                currency=None,
                notes="missing_data",
                source_refs=_fallback_evidence(state),
            )
        )
    if statement.statement_type != kind:
        statement.statement_type = kind
    for item in statement.line_items:
        if not item.source_refs:
            item.source_refs = _fallback_evidence(state)
    return statement


def _fallback_evidence(state: AgentState) -> list[SourceRef]:
    if state.pages:
        snippet = state.pages[0].text.strip().split("\n")[0][:200]
        return [SourceRef(ref_type="page_text", page=1, table_id=None, quote=snippet, confidence=0.2)]
    return [SourceRef(ref_type="page_text", page=1, table_id=None, quote="Evidence unavailable", confidence=0.1)]


def _build_statement_prompt(state: AgentState, kind: str) -> str:
    context = "\n".join(chunk.text[:500] for chunk in state.chunks[:3])
    return f"Extract {kind} statement from the context.\nContext:\n{context}"


def _build_notes_prompt(state: AgentState) -> str:
    context = "\n".join(chunk.text[:500] for chunk in state.chunks[:3])
    return f"Extract key notes with evidence.\nContext:\n{context}"


def _validate_notes(data: Any, state: AgentState) -> list[KeyNote]:
    notes: list[KeyNote] = []
    for raw in data if isinstance(data, list) else []:
        try:
            note = KeyNote.model_validate(raw)
            if not note.source_refs:
                note.source_refs = _fallback_evidence(state)
            notes.append(note)
        except ValidationError:
            continue
    return notes


def _build_signals_prompt(state: AgentState) -> str:
    return "Generate additional risk signals with evidence if possible."


def _build_report_prompt(state: AgentState) -> str:
    return "Generate a trader report JSON with summary, drivers, and limitations."


def _numbers_snapshot(state: AgentState) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for statement in state.statements.values():
        snapshot.update(statement.totals)
    return snapshot


def _statement_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "statement_type": {"type": "string"},
            "period_end": {"type": ["string", "null"]},
            "period_start": {"type": ["string", "null"]},
            "line_items": {"type": "array"},
            "totals": {"type": "object"},
            "extraction_confidence": {"type": "number"},
            "issues": {"type": "array"},
        },
        "required": ["statement_type", "line_items", "totals", "extraction_confidence", "issues"],
    }


def _key_notes_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "note_type": {"type": "string"},
                "summary": {"type": "string"},
                "source_refs": {"type": "array"},
            },
            "required": ["note_type", "summary", "source_refs"],
        },
    }


def _risk_signals_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "signal_id": {"type": "string"},
                "category": {"type": "string"},
                "title": {"type": "string"},
                "severity": {"type": "string"},
                "description": {"type": "string"},
                "metrics": {"type": "object"},
                "evidence": {"type": "array"},
            },
            "required": ["signal_id", "category", "title", "severity", "description", "metrics", "evidence"],
        },
    }


def _trader_report_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string"},
            "executive_summary": {"type": "string"},
            "key_drivers": {"type": "array"},
            "numbers_snapshot": {"type": "object"},
            "risk_signals": {"type": "array"},
            "notes": {"type": "array"},
            "limitations": {"type": "array"},
            "created_at": {"type": ["string", "null"]},
        },
        "required": ["executive_summary", "key_drivers", "numbers_snapshot", "limitations"],
    }


def _render_markdown_report(state: AgentState) -> str:
    report = state.trader_report
    if not report:
        return ""
    lines = [
        f"# Trader Report for {state.doc_meta.filename}",
        "",
        "## Executive Summary",
        report.executive_summary,
        "",
        "## Key Drivers",
    ]
    for driver in report.key_drivers:
        lines.append(f"- {driver}")
    lines.extend(["", "## Numbers Snapshot"])
    for key, value in report.numbers_snapshot.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Risk Signals"])
    for signal in report.risk_signals:
        lines.append(f"- {signal.title} ({signal.severity}): {signal.description}")
        for ref in signal.evidence:
            lines.append(f"  - Evidence: page {ref.page} ({ref.ref_type}) {ref.quote or ''}")
    lines.extend(["", "## Notes"])
    for note in report.notes:
        lines.append(f"- {note.note_type}: {note.summary}")
        for ref in note.source_refs:
            lines.append(f"  - Evidence: page {ref.page} ({ref.ref_type}) {ref.quote or ''}")
    lines.extend(["", "## Limitations", "- Not financial advice."])
    for limitation in report.limitations:
        lines.append(f"- {limitation}")
    lines.append(f"\nGenerated at {report.created_at.isoformat()}.")
    return "\n".join(lines)
