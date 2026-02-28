from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.agent.state import AgentState
from src.finance.normalizer import normalize_account_name
from src.finance.signals import generate_signals
from src.finance.utils import table_rows
from src.finance.validators import validate_statements
from src.llm.base import StructuredPromptRequest, get_default_llm_client, langsmith_metadata
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
from src.storage.vector_index import LocalVectorIndex, build_rag_index
from src.utils.ids import new_doc_id
from src.utils.logging import get_logger, log_node
from src.utils.time import monotonic_ms


logger = get_logger(__name__)


class KeyNotesBundle(BaseModel):
    notes: list[KeyNote] = Field(default_factory=list)


class RiskSignalsBundle(BaseModel):
    risk_signals: list[RiskSignal] = Field(default_factory=list)


class TraderReportDraft(BaseModel):
    executive_summary: str = ""
    key_drivers: list[str] = Field(default_factory=list)
    numbers_snapshot: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


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

            # OCR integration: supplement sparse pages with OCR text
            if result.needs_ocr and result.ocr_page_indices and state.pdf_path:
                _apply_ocr_to_pages(state, result.ocr_page_indices, store)
        except Exception as exc:
            state.errors.append(f"ingest_failed:{exc}")
            state.pages = []
            state.needs_ocr = False

    state.debug["page_count"] = len(state.pages)
    if os.getenv("DEBUG") == "1":
        store.save_json(state.doc_meta.doc_id, "extracted/pages.json", [p.model_dump() for p in state.pages])
    log_node(logger, state.doc_meta.doc_id, "ingest_pdf", start_ms)
    return state


def _apply_ocr_to_pages(state: AgentState, ocr_page_indices: list[int], store: LocalStore) -> None:
    """Run OCR on sparse pages and update state.pages in-place."""
    try:
        from src.pdf.ocr import get_ocr_engine
        from src.pdf.render import render_page
    except Exception:
        return

    lang = state.doc_meta.language or "auto"
    engine = get_ocr_engine(lang)
    if engine is None:
        state.debug["ocr_skipped"] = "no_engine_available"
        return

    pages_dir = str(store.ensure_layout(state.doc_meta.doc_id)["pages"])
    ocr_count = 0
    for page_idx in ocr_page_indices:
        if page_idx >= len(state.pages):
            continue
        page = state.pages[page_idx]
        try:
            img_path = render_page(
                state.pdf_path or "",
                page_number=page.page_number,
                out_dir=pages_dir,
                dpi=200,
            )
            results = engine.recognize(img_path, lang=lang)
            ocr_text = " ".join(r.text for r in results if r.text)
            if ocr_text.strip():
                state.pages[page_idx] = Page(
                    page_number=page.page_number,
                    text=ocr_text,
                    images=[img_path] + [i for i in page.images if i != img_path],
                )
                ocr_count += 1
        except Exception as exc:
            state.errors.append(f"ocr_page_{page.page_number}_failed:{exc}")

    state.debug["ocr_pages_processed"] = ocr_count


def extract_tables(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    if state.pdf_path and "fake_pages" not in state.debug:
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

    # Support both English and Chinese heading formats
    heading_pattern = re.compile(
        r"^("
        r"\d+\.|"                                           # 1. 2. 3.
        r"[IVX]+\.|"                                        # I. II. III.
        r"[A-Z][A-Za-z\s]{2,}|"                             # English Title Case
        r"[一二三四五六七八九十]+[、.]|"                      # 一、 二、
        r"（[一二三四五六七八九十]+）|"                       # （一） （二）
        r"第[一二三四五六七八九十\d]+[章节篇部分条]"          # 第一章 第二节
        r")"
    )

    for page in state.pages:
        lines = page.text.splitlines()
        for line in lines:
            line_text = line.strip()
            if heading_pattern.match(line_text):
                # When a new heading is detected, flush the current chunk
                if current_text.strip():
                    chunks.extend(
                        _build_chunks_from_text(
                            current_text,
                            current_start,
                            page.page_number,
                            current_section,
                        )
                    )
                    current_text = ""
                    current_start = page.page_number
                current_section = line_text

        if len(current_text) + len(page.text) > 1500 and current_text:
            chunks.extend(
                _build_chunks_from_text(
                    current_text,
                    current_start,
                    page.page_number - 1,
                    current_section,
                )
            )
            current_text = ""
            current_start = page.page_number
        current_text += page.text + "\n"

    if current_text.strip():
        chunks.extend(
            _build_chunks_from_text(
                current_text,
                current_start,
                state.pages[-1].page_number if state.pages else 1,
                current_section,
            )
        )

    state.chunks = chunks
    state.debug["chunk_count"] = len(chunks)
    log_node(logger, state.doc_meta.doc_id, "detect_sections_and_chunk", start_ms)
    return state


def extract_financial_statements(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    statements: dict[str, FinancialStatement] = {}
    tables_by_type = {"balance": [], "income": [], "cashflow": []}

    # Build retry context from previous validation failures
    retry_context = ""
    if state.retry_count > 0 and state.validation_results:
        prev_issues = state.validation_results.get("issues", [])
        prev_checks = state.validation_results.get("checks", {})
        if prev_issues:
            retry_context = (
                f"IMPORTANT: Previous extraction attempt failed validation "
                f"(retry {state.retry_count}). Issues found: {', '.join(prev_issues)}. "
                f"Checks: {json.dumps(prev_checks)}. "
                f"Please pay extra attention to these problems and ensure "
                f"totals are consistent (assets = liabilities + equity), "
                f"units are uniform, and all key fields are populated."
            )

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
            statements[kind] = _llm_statement(state, kind, retry_context=retry_context)

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
    # Remove any previous validation_failed entries before deciding, ensuring idempotency
    state.errors = [err for err in state.errors if err != "validation_failed"]
    if severe:
        state.errors.append("validation_failed")
        state.retry_count += 1
    log_node(logger, state.doc_meta.doc_id, "validate_and_reconcile", start_ms)
    return state


def extract_key_notes(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    system = _load_prompt("key_notes_prompt.md")
    context = _build_rag_context(
        state,
        query=(
            "accounting policy audit opinion related party impairment contingency "
            "segment guidance disclosure"
        ),
        top_k=8,
    )

    shared_inputs = {"context": context}
    requests = {
        "main_notes": StructuredPromptRequest(
            system_template=system,
            user_template=(
                "Use only the retrieved context below to extract key notes.\n"
                "Context:\n{context}\n"
                "Return an object: {{'notes': [KeyNote, ...]}}."
            ),
            input_values=shared_inputs,
            output_model=KeyNotesBundle,
        ),
        "audit_notes": StructuredPromptRequest(
            system_template=system,
            user_template=(
                "Focus on governance, audit language, and cautionary disclosures.\n"
                "Context:\n{context}\n"
                "Return an object: {{'notes': [KeyNote, ...]}}."
            ),
            input_values=shared_inputs,
            output_model=KeyNotesBundle,
        ),
    }

    outputs = _call_llm_parallel_structured(
        state,
        requests,
        node_name="extract_key_notes",
    )
    notes: list[KeyNote] = []
    for key in ("main_notes", "audit_notes"):
        bundle = _to_notes_bundle(outputs.get(key))
        notes.extend(bundle.notes)

    notes = _dedupe_notes(notes)
    if not notes:
        notes.append(KeyNote(note_type="other", summary="No notes extracted.", source_refs=_fallback_evidence(state)))

    for note in notes:
        if not note.source_refs:
            note.source_refs = _fallback_evidence(state)

    state.notes = notes
    state.debug["notes_count"] = len(notes)
    log_node(logger, state.doc_meta.doc_id, "extract_key_notes", start_ms)
    return state


def generate_risk_signals(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    pages_text = [page.text for page in state.pages]
    signals = generate_signals(state.statements, state.notes, state.validation_results, pages_text)

    system = _load_prompt("trader_report_prompt.md")
    context = _build_rag_context(
        state,
        query="risk signals cashflow net income working capital disclosure audit",
        top_k=8,
    )

    shared_inputs = {
        "context": context,
        "existing_signals": json.dumps([signal.model_dump() for signal in signals], ensure_ascii=False),
        "validation_issues": ",".join(state.validation_results.get("issues", [])),
    }

    requests = {
        "additional_signals": StructuredPromptRequest(
            system_template=system,
            user_template=(
                "Identify additional risk signals from the context and validation issues.\n"
                "Validation issues: {validation_issues}\n"
                "Context:\n{context}\n"
                "Return an object: {{'risk_signals': [RiskSignal, ...]}}."
            ),
            input_values=shared_inputs,
            output_model=RiskSignalsBundle,
        ),
        "signal_explanations": StructuredPromptRequest(
            system_template=system,
            user_template=(
                "Improve explanations for these existing signals while keeping categories grounded in context.\n"
                "Existing signals JSON:\n{existing_signals}\n"
                "Context:\n{context}\n"
                "Return an object: {{'risk_signals': [RiskSignal, ...]}}."
            ),
            input_values=shared_inputs,
            output_model=RiskSignalsBundle,
        ),
    }

    outputs = _call_llm_parallel_structured(
        state,
        requests,
        node_name="generate_risk_signals",
    )

    additional = _to_risk_signals_bundle(outputs.get("additional_signals")).risk_signals
    enriched = _to_risk_signals_bundle(outputs.get("signal_explanations")).risk_signals

    signals = _merge_signals(signals + additional + enriched)
    for signal in signals:
        if not signal.evidence:
            signal.evidence = _fallback_evidence(state)

    state.risk_signals = signals
    state.debug["signals_count"] = len(signals)
    log_node(logger, state.doc_meta.doc_id, "generate_risk_signals", start_ms)
    return state


def build_trader_report(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    system = _load_prompt("trader_report_prompt.md")
    context = _build_rag_context(
        state,
        query="executive summary key drivers financial snapshot risk limitations",
        top_k=10,
    )

    snapshot = _numbers_snapshot(state)
    request = StructuredPromptRequest(
        system_template=system,
        user_template=(
            "Document metadata JSON:\n{doc_meta}\n"
            "Validation JSON:\n{validation_results}\n"
            "Risk signals JSON:\n{risk_signals}\n"
            "Notes JSON:\n{notes}\n"
            "Retrieved context:\n{context}\n"
            "Current numbers snapshot JSON:\n{numbers_snapshot}\n"
            "Return a concise report object with fields: executive_summary, key_drivers, "
            "numbers_snapshot, limitations."
        ),
        input_values={
            "doc_meta": json.dumps(state.doc_meta.model_dump(mode="json"), ensure_ascii=False),
            "validation_results": json.dumps(state.validation_results, ensure_ascii=False),
            "risk_signals": json.dumps([s.model_dump() for s in state.risk_signals], ensure_ascii=False),
            "notes": json.dumps([n.model_dump() for n in state.notes], ensure_ascii=False),
            "context": context,
            "numbers_snapshot": json.dumps(snapshot, ensure_ascii=False),
        },
        output_model=TraderReportDraft,
    )

    draft = _call_llm_structured(
        state,
        request,
        node_name="build_trader_report",
        fallback=TraderReportDraft(
            executive_summary=f"Parsed {len(state.pages)} pages for {state.doc_meta.filename}.",
            key_drivers=["See extracted statements and notes."],
            numbers_snapshot=snapshot,
            limitations=["Not financial advice.", "Outputs depend on PDF extraction quality."],
        ),
    )

    report = TraderReport(
        doc_id=state.doc_meta.doc_id,
        executive_summary=draft.executive_summary or f"Parsed {len(state.pages)} pages for {state.doc_meta.filename}.",
        key_drivers=draft.key_drivers or ["See extracted statements and notes."],
        numbers_snapshot=draft.numbers_snapshot or snapshot,
        risk_signals=state.risk_signals,
        notes=state.notes,
        limitations=sorted(
            set(
                [
                    "Not financial advice.",
                    "Outputs depend on PDF extraction quality.",
                ]
                + draft.limitations
            )
        ),
    )

    state.trader_report = report
    state.debug["report_ready"] = True
    log_node(logger, state.doc_meta.doc_id, "build_trader_report", start_ms)
    return state


def finalize(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    # Remove non-serializable cached objects from debug before saving
    state.debug.pop("_rag_index", None)

    store = LocalStore(state.data_dir or "data")
    store.save_meta(state.doc_meta.doc_id, state.doc_meta)
    store.save_json(state.doc_meta.doc_id, "extracted/pages.json", [p.model_dump() for p in state.pages])
    store.save_json(state.doc_meta.doc_id, "extracted/tables.json", [t.model_dump() for t in state.tables])
    store.save_json(state.doc_meta.doc_id, "extracted/statements.json", {k: v.model_dump() for k, v in state.statements.items()})
    store.save_json(state.doc_meta.doc_id, "extracted/notes.json", [n.model_dump() for n in state.notes])
    store.save_json(state.doc_meta.doc_id, "extracted/risk_signals.json", [s.model_dump() for s in state.risk_signals])
    if state.trader_report:
        store.save_json(
            state.doc_meta.doc_id,
            "report/trader_report.json",
            state.trader_report.model_dump(mode="json"),
        )
        store.save_markdown(state.doc_meta.doc_id, "report/trader_report.md", _render_markdown_report(state))
    log_node(logger, state.doc_meta.doc_id, "finalize", start_ms)
    return state


def _build_chunks_from_text(text: str, start: int, end: int, section: str | None) -> list[Chunk]:
    chunks: list[Chunk] = []
    for part in _split_text(text.strip(), target_size=1200):
        if not part.strip():
            continue
        snippet = part.strip().split("\n")[0][:200]
        source = SourceRef(ref_type="page_text", page=start, table_id=None, quote=snippet, confidence=0.4)
        chunks.append(
            Chunk(
                chunk_id=new_doc_id(),
                page_start=start,
                page_end=end,
                section=section,
                text=part.strip(),
                bbox=None,
                source_refs=[source],
            )
        )
    return chunks


def _split_text(text: str, target_size: int) -> list[str]:
    if len(text) <= target_size:
        return [text]
    parts: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        # If a single paragraph exceeds target_size, split it further by sentences
        if len(paragraph) > target_size:
            if current:
                parts.append(current)
                current = ""
            for chunk in _split_long_paragraph(paragraph, target_size):
                parts.append(chunk)
            continue
        next_block = (current + "\n\n" + paragraph).strip() if current else paragraph
        if len(next_block) > target_size and current:
            parts.append(current)
            current = paragraph
        else:
            current = next_block
    if current:
        parts.append(current)
    return parts


def _split_long_paragraph(text: str, target_size: int) -> list[str]:
    """Split a long paragraph by sentence boundaries, falling back to hard cuts."""
    sentences = re.split(r"(?<=[。！？.!?\n])", text)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = current + sentence
        if len(candidate) > target_size and current:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    while len(current) > target_size:
        parts.append(current[:target_size])
        current = current[target_size:]
    if current:
        parts.append(current)
    return parts


def _detect_statement_type(table: Table) -> str | None:
    balance_keywords = ["balance sheet", "statement of financial position", "资产负债表"]
    income_keywords = ["income statement", "profit and loss", "statement of operations", "利润表"]
    cashflow_keywords = ["cash flow", "statement of cash flows", "现金流量表"]

    # Check table title first (cheapest check)
    if table.title:
        title_lower = table.title.lower()
        if any(kw in title_lower for kw in balance_keywords):
            return "balance"
        if any(kw in title_lower for kw in income_keywords):
            return "income"
        if any(kw in title_lower for kw in cashflow_keywords):
            return "cashflow"

    # Fall back to checking only the first few rows of cells
    n_cols = table.n_cols or 1
    max_cells = n_cols * 3  # first 3 rows
    header_cells = table.cells[:max_cells] if len(table.cells) > max_cells else table.cells
    text = " ".join(cell.text for cell in header_cells).lower()

    if any(kw in text for kw in balance_keywords):
        return "balance"
    if any(kw in text for kw in income_keywords):
        return "income"
    if any(kw in text for kw in cashflow_keywords):
        return "cashflow"
    return None


def _tables_to_statement(kind: str, tables: list[Table]) -> FinancialStatement:
    line_items: list[StatementLineItem] = []
    totals: dict[str, float] = {}
    for table in tables:
        rows = table_rows(table)
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
                source_refs=list(table.source_refs),
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
        extraction_confidence=0.65,
        issues=[],
    )


_UNIT_MULTIPLIERS = {
    "万元": 1e4,
    "亿元": 1e8,
    "百万": 1e6,
    "千万": 1e7,
    "万": 1e4,
    "亿": 1e8,
}

# Characters that indicate negative values in Chinese financial reports
_NEGATIVE_MARKERS = re.compile(r"^[△▲\-－]")


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.replace(",", "").replace(" ", "").strip()
    if not text:
        return None

    # Handle parenthetical negatives: (1234.56) or （1234.56）
    negative = False
    if (text.startswith("(") and text.endswith(")")) or (text.startswith("（") and text.endswith("）")):
        negative = True
        text = text[1:-1].strip()

    # Handle leading negative markers: △, ▲, -, －
    if not negative and _NEGATIVE_MARKERS.match(text):
        negative = True
        text = _NEGATIVE_MARKERS.sub("", text).strip()

    # Strip percentage sign (return as decimal proportion)
    is_percent = False
    if text.endswith("%") or text.endswith("％"):
        is_percent = True
        text = text[:-1].strip()

    # Strip currency symbols
    text = text.lstrip("$¥￥€£＄")

    # Check for Chinese unit suffixes and apply multiplier
    multiplier = 1.0
    for unit, mult in _UNIT_MULTIPLIERS.items():
        if text.endswith(unit):
            multiplier = mult
            text = text[: -len(unit)].strip()
            break

    try:
        num = float(text)
    except ValueError:
        return None

    if is_percent:
        num /= 100.0

    num *= multiplier
    return -num if negative else num


def _load_prompt(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _llm_statement(state: AgentState, kind: str, *, retry_context: str = "") -> FinancialStatement:
    system = _load_prompt("statement_extraction_prompt.md")
    context = _build_rag_context(
        state,
        query=f"{kind} statement line items totals current prior period",
        top_k=10,
    )

    user_template = (
        "Target statement type: {statement_type}.\n"
        "Use only this context:\n{context}\n"
    )
    input_values: dict[str, str] = {"statement_type": kind, "context": context}

    if retry_context:
        user_template += "{retry_context}\n"
        input_values["retry_context"] = retry_context

    user_template += "Return one FinancialStatement object."

    request = StructuredPromptRequest(
        system_template=system,
        user_template=user_template,
        input_values=input_values,
        output_model=FinancialStatement,
    )

    statement = _call_llm_structured(
        state,
        request,
        node_name="extract_financial_statements",
        fallback=FinancialStatement(
            statement_type=kind,
            period_end=None,
            period_start=None,
            line_items=[],
            totals={},
            extraction_confidence=0.2,
            issues=["llm_parse_failed"],
        ),
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


def _call_llm_structured(
    state: AgentState,
    request: StructuredPromptRequest,
    *,
    node_name: str,
    fallback: Any,
) -> Any:
    client = get_default_llm_client()
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            return client.invoke_structured(
                request,
                run_name=node_name,
                tags=["financial-report-agent", node_name],
                metadata=langsmith_metadata(
                    state.doc_meta.doc_id,
                    node_name,
                    attempt=attempt + 1,
                ),
            )
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        state.errors.append(f"{node_name}_llm_failed:{last_error}")
    return fallback


def _call_llm_parallel_structured(
    state: AgentState,
    requests: dict[str, StructuredPromptRequest],
    *,
    node_name: str,
) -> dict[str, Any]:
    client = get_default_llm_client()
    results: dict[str, Any] = {}
    remaining = dict(requests)

    for attempt in range(2):
        failed: dict[str, StructuredPromptRequest] = {}
        for key, request in remaining.items():
            try:
                results[key] = client.invoke_structured(
                    request,
                    run_name=f"{node_name}.{key}",
                    tags=["financial-report-agent", node_name, "parallel"],
                    metadata=langsmith_metadata(
                        state.doc_meta.doc_id,
                        node_name,
                        attempt=attempt + 1,
                        branch=key,
                    ),
                )
            except Exception:
                failed[key] = request
        if not failed:
            break
        remaining = failed

    if remaining:
        state.errors.append(f"{node_name}_llm_parallel_failed:{list(remaining.keys())}")
    return results


def _build_rag_context(state: AgentState, query: str, *, top_k: int) -> str:
    # Cache the vector index in state.debug to avoid rebuilding on each call
    cached_index = state.debug.get("_rag_index")
    if cached_index is None:
        lang = state.doc_meta.language or "auto"
        cached_index = build_rag_index(state.chunks, state.tables, lang=lang)
        state.debug["_rag_index"] = cached_index

    docs = cached_index.search(query, k=top_k)

    retrieval_debug = state.debug.setdefault("retrieval", {})
    retrieval_debug[query] = {
        "indexed_docs": cached_index.size,
        "returned_docs": len(docs),
    }

    if not docs:
        fallback = "\n".join(chunk.text for chunk in state.chunks[:3])
        return fallback[:4000]

    lines: list[str] = []
    for idx, doc in enumerate(docs, start=1):
        metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
        page = metadata.get("page") or metadata.get("page_start")
        table_id = metadata.get("table_id")
        source_type = metadata.get("source_type", "unknown")
        lines.append(
            f"[Doc {idx}] source_type={source_type} page={page} table_id={table_id}\n"
            f"{doc.page_content[:900]}"
        )
    return "\n\n".join(lines)


def _to_notes_bundle(raw: Any) -> KeyNotesBundle:
    if isinstance(raw, KeyNotesBundle):
        return raw
    if isinstance(raw, dict):
        try:
            return KeyNotesBundle.model_validate(raw)
        except ValidationError:
            pass
    if isinstance(raw, list):
        return KeyNotesBundle(notes=_validate_note_list(raw))
    return KeyNotesBundle()


def _to_risk_signals_bundle(raw: Any) -> RiskSignalsBundle:
    if isinstance(raw, RiskSignalsBundle):
        return raw
    if isinstance(raw, dict):
        try:
            return RiskSignalsBundle.model_validate(raw)
        except ValidationError:
            pass
    if isinstance(raw, list):
        return RiskSignalsBundle(risk_signals=_validate_signal_list(raw))
    return RiskSignalsBundle()


def _validate_note_list(raw_items: list[Any]) -> list[KeyNote]:
    notes: list[KeyNote] = []
    for raw in raw_items:
        try:
            notes.append(KeyNote.model_validate(raw))
        except ValidationError:
            continue
    return notes


def _validate_signal_list(raw_items: list[Any]) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    for raw in raw_items:
        try:
            signals.append(RiskSignal.model_validate(raw))
        except ValidationError:
            continue
    return signals


def _dedupe_notes(notes: list[KeyNote]) -> list[KeyNote]:
    deduped: list[KeyNote] = []
    seen: set[tuple[str, str]] = set()
    for note in notes:
        key = (note.note_type, note.summary.strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(note)
    return deduped


def _merge_signals(signals: list[RiskSignal]) -> list[RiskSignal]:
    merged: list[RiskSignal] = []
    by_key: dict[tuple[str, str], int] = {}

    for signal in signals:
        key = (signal.category, signal.title.strip())
        if key not in by_key:
            by_key[key] = len(merged)
            merged.append(signal)
            continue

        idx = by_key[key]
        existing = merged[idx]
        evidence = existing.evidence or []
        if signal.evidence:
            evidence = _merge_evidence(evidence, signal.evidence)
        merged[idx] = RiskSignal(
            signal_id=existing.signal_id,
            category=existing.category,
            title=existing.title,
            severity=_pick_more_severe(existing.severity, signal.severity),
            description=signal.description if len(signal.description) > len(existing.description) else existing.description,
            metrics={**existing.metrics, **signal.metrics},
            evidence=evidence,
        )
    return merged


def _merge_evidence(base: list[SourceRef], extra: list[SourceRef]) -> list[SourceRef]:
    merged = list(base)
    seen = {(item.ref_type, item.page, item.table_id, item.quote) for item in merged}
    for item in extra:
        key = (item.ref_type, item.page, item.table_id, item.quote)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _pick_more_severe(left: str, right: str) -> str:
    rank = {"low": 1, "medium": 2, "high": 3}
    return left if rank.get(left, 1) >= rank.get(right, 1) else right


def _fallback_evidence(state: AgentState) -> list[SourceRef]:
    if state.pages:
        snippet = state.pages[0].text.strip().split("\n")[0][:200]
        return [SourceRef(ref_type="page_text", page=1, table_id=None, quote=snippet, confidence=0.2)]
    return [SourceRef(ref_type="page_text", page=1, table_id=None, quote="Evidence unavailable", confidence=0.1)]


def _numbers_snapshot(state: AgentState) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for statement in state.statements.values():
        snapshot.update(statement.totals)
    return snapshot


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

    lines.extend(["", "## Limitations"])
    for limitation in report.limitations:
        lines.append(f"- {limitation}")

    lines.append(f"\nGenerated at {report.created_at.isoformat()}.")
    return "\n".join(lines)
