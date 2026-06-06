"""PDF ingestion and preprocessing pipeline nodes."""
from __future__ import annotations

import os
import re

from src.agent.state import AgentState
from src.schemas.models import Chunk, Page, SourceRef
from src.storage.backend import StorageBackend, get_storage_backend
from src.pdf.extractor import PDFExtractor
from src.pdf.tables import extract_tables as extract_tables_from_pdf
from src.utils.ids import new_doc_id
from src.utils.logging import get_logger, log_node
from src.utils.time import monotonic_ms


logger = get_logger(__name__)


def ingest_pdf(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    data_dir = state.data_dir or "data"
    store = get_storage_backend(data_dir)

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
        store.save_json(state.doc_meta.doc_id, "extracted/pages.json", [p.model_dump(mode="json") for p in state.pages])
    log_node(logger, state.doc_meta.doc_id, "ingest_pdf", start_ms)
    return state


def _apply_ocr_to_pages(state: AgentState, ocr_page_indices: list[int], store: StorageBackend) -> None:
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
