"""Table extraction with pluggable engines and automatic routing.

Supports multiple extraction back-ends via the :class:`TableEngine` Protocol.
The :func:`extract_tables` router selects the best engine based on
``TABLE_ENGINE`` env var (``auto``, ``pdfplumber``, ``camelot``, ``best``).

Cross-page table merging is applied after extraction to reunite tables
that span page boundaries.
"""
from __future__ import annotations

import os
import structlog
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from src.schemas.models import SourceRef, Table, TableCell

logger = structlog.get_logger()


# ── Protocol ─────────────────────────────────────────────────────────────────


@runtime_checkable
class TableEngine(Protocol):
    """Interface that every table extraction engine must satisfy."""

    name: str

    def extract(self, pdf_path: str) -> list[Table]:
        """Extract tables from a PDF file."""
        ...


# ── Pdfplumber Engine ────────────────────────────────────────────────────────


class PdfplumberEngine:
    """Table extraction using pdfplumber (default, works on most PDFs)."""

    name = "pdfplumber"

    def extract(self, pdf_path: str) -> list[Table]:
        try:
            import pdfplumber  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("pdfplumber is required for table extraction") from exc

        tables: list[Table] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                page_tables = page.find_tables() or []
                for table_index, page_table in enumerate(page_tables, start=1):
                    raw_table = page_table.extract() or []
                    if not raw_table:
                        continue
                    table = _raw_to_table(
                        raw_table,
                        page_index=page_index,
                        table_index=table_index,
                        engine_name=self.name,
                        page_width=page.width,
                        page_height=page.height,
                        page_table_obj=page_table,
                    )
                    tables.append(table)
        return tables


# ── Camelot Engine ───────────────────────────────────────────────────────────


class CamelotEngine:
    """Table extraction using camelot-py (better for bordered tables).

    Requires the ``tables`` extra: ``pip install financial-report-agent[tables]``.
    Uses the *lattice* flavour first, falling back to *stream* for
    borderless tables.
    """

    name = "camelot"

    def extract(self, pdf_path: str) -> list[Table]:
        try:
            import camelot  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "camelot-py is required for CamelotEngine. "
                "Install with: pip install financial-report-agent[tables]"
            ) from exc

        tables: list[Table] = []
        # Try lattice first (bordered tables), then stream (borderless)
        for flavour in ("lattice", "stream"):
            try:
                camelot_tables = camelot.read_pdf(
                    pdf_path,
                    flavor=flavour,
                    pages="all",
                    suppress_stdout=True,
                )
            except Exception:
                continue

            for idx, ct in enumerate(camelot_tables, start=1):
                if ct.accuracy < 10:
                    continue  # skip very low-confidence tables
                raw = ct.data  # list[list[str]]
                if not raw:
                    continue
                page_num = ct.page  # camelot page numbers are 1-based
                # Avoid duplicates: skip if we already extracted this page+region
                if flavour == "stream" and _overlaps_existing(tables, page_num, raw):
                    continue
                table = _raw_to_table(
                    raw,
                    page_index=page_num,
                    table_index=len(tables) + 1,
                    engine_name=self.name,
                    page_width=0,
                    page_height=0,
                    page_table_obj=None,
                    camelot_accuracy=ct.accuracy,
                )
                tables.append(table)
        return tables


def _overlaps_existing(
    existing: list[Table], page: int, raw: list[list[str | None]]
) -> bool:
    """Return True if a candidate table overlaps an already-extracted one."""
    for t in existing:
        if t.page != page:
            continue
        # Simple heuristic: same page and similar row count → likely duplicate
        if abs(t.n_rows - len(raw)) <= 1:
            return True
    return False


# ── Router ───────────────────────────────────────────────────────────────────

_ENGINES: dict[str, type[PdfplumberEngine | CamelotEngine]] = {
    "pdfplumber": PdfplumberEngine,
    "camelot": CamelotEngine,
}


def extract_tables(
    pdf_path: str,
    *,
    engine: str | None = None,
    merge_cross_page: bool = True,
) -> list[Table]:
    """Extract tables from a PDF using the configured engine.

    Parameters
    ----------
    pdf_path:
        Path to the PDF file.
    engine:
        Override engine selection. One of ``pdfplumber``, ``camelot``,
        ``best``, or ``auto``.  ``None`` reads from ``TABLE_ENGINE`` env var
        (default ``auto``).
    merge_cross_page:
        When True, attempt to merge tables that span page boundaries.

    Returns
    -------
    list[Table]
        Extracted (and optionally merged) tables.
    """
    requested_engine = engine or os.getenv("TABLE_ENGINE") or "auto"
    mode = requested_engine.lower()

    if mode == "auto":
        tables = _extract_with_engine(pdf_path, PdfplumberEngine())
    elif mode == "best":
        tables = _extract_best(pdf_path)
    elif mode in _ENGINES:
        tables = _extract_with_engine(pdf_path, _ENGINES[mode]())
    else:
        logger.warning("unknown_table_engine", engine=mode, fallback="auto")
        tables = _extract_with_engine(pdf_path, PdfplumberEngine())

    if merge_cross_page and len(tables) > 1:
        tables = merge_cross_page_tables(tables)

    return tables


def _extract_with_engine(pdf_path: str, eng: TableEngine) -> list[Table]:
    """Run extraction with a single engine, logging any errors."""
    try:
        result = eng.extract(pdf_path)
        logger.info("table_extraction_done", engine=eng.name, count=len(result))
        return result
    except Exception as exc:
        logger.warning("table_extraction_failed", engine=eng.name, error=str(exc))
        return []


def _extract_best(pdf_path: str) -> list[Table]:
    """Try all available engines and pick the one with the best results.

    Prefers camelot for bordered tables (higher accuracy score), falls
    back to pdfplumber when camelot is unavailable or produces fewer tables.
    """
    results: list[tuple[str, list[Table]]] = []

    # Always try pdfplumber
    plumber_tables = _extract_with_engine(pdf_path, PdfplumberEngine())
    results.append(("pdfplumber", plumber_tables))

    # Try camelot if available
    try:
        camelot_tables = _extract_with_engine(pdf_path, CamelotEngine())
        if camelot_tables:
            results.append(("camelot", camelot_tables))
    except Exception as exc:
        logger.warning("table_router_camelot_failed", error=str(exc))

    # Pick the result set with the highest average confidence
    best_name, best_tables = max(
        results,
        key=lambda r: (
            len(r[1]),
            _avg_confidence(r[1]),
        ),
    )
    logger.info("table_router_best", engine=best_name, count=len(best_tables))
    return best_tables


def _avg_confidence(tables: list[Table]) -> float:
    if not tables:
        return 0.0
    total = sum(
        sr.confidence
        for t in tables
        for sr in t.source_refs
        if sr.confidence is not None
    )
    count = sum(1 for t in tables for sr in t.source_refs)
    return total / max(count, 1)


# ── Cross-page table merging ─────────────────────────────────────────────────


def merge_cross_page_tables(tables: list[Table]) -> list[Table]:
    """Merge tables that appear to continue across page boundaries.

    Heuristics for continuation:
    1. Tables on consecutive pages (page N and page N+1).
    2. Same column count.
    3. The continuation table has no title (title row is on the first page).
    4. The first row of the continuation matches the base header or is data.
    """
    if len(tables) <= 1:
        return tables

    merged: list[Table] = []
    i = 0
    while i < len(tables):
        current = tables[i]
        last_page = current.page
        # Look ahead for continuation tables
        j = i + 1
        while j < len(tables):
            # Use last_page (not current.page) so multi-page chains work
            if _is_continuation_at_page(current, tables[j], last_page):
                current = _merge_two_tables(current, tables[j])
                last_page = tables[j].page
                j += 1
            else:
                break
        merged.append(current)
        i = j

    return merged


def _is_continuation_at_page(base: Table, candidate: Table, expected_page: int) -> bool:
    """Check if *candidate* continues *base* from *expected_page*."""
    if candidate.page != expected_page + 1:
        return False
    if abs(candidate.n_cols - base.n_cols) > 1:
        return False
    if candidate.title is not None:
        return False
    first_row_cells = sorted(
        [c for c in candidate.cells if c.row == 0], key=lambda c: c.col
    )
    first_row_text = [c.text or "" for c in first_row_cells]
    if not any(first_row_text):
        return True
    if is_header_row(first_row_text):
        base_header_cells = sorted(
            [c for c in base.cells if c.row == 0], key=lambda c: c.col
        )
        base_header_text = [c.text or "" for c in base_header_cells]
        if first_row_text == base_header_text:
            return True
        return False
    return True


def _merge_two_tables(base: Table, cont: Table) -> Table:
    """Merge a continuation table into the base table."""
    row_offset = base.n_rows

    # Offset continuation cells
    shifted_cells = [
        TableCell(
            row=c.row + row_offset,
            col=c.col,
            text=c.text,
            rowspan=c.rowspan,
            colspan=c.colspan,
            bbox=c.bbox,
            confidence=c.confidence,
            engine=c.engine or cont.source_refs[0].engine if cont.source_refs else c.engine,
        )
        for c in cont.cells
        # Skip header row from continuation if present
        if c.row > 0 or not is_header_row(
            [cc.text or None for cc in cont.cells if cc.row == c.row]
        )
    ]

    all_cells = base.cells + shifted_cells
    n_rows = base.n_rows + len({c.row for c in shifted_cells})
    n_cols = max(base.n_cols, cont.n_cols)

    # Rebuild markdown
    raw_rows = _cells_to_raw_rows(all_cells, n_rows, n_cols)
    raw_md = _table_to_markdown(raw_rows)

    # Combine source refs
    source_refs = list(base.source_refs) + list(cont.source_refs)

    # Update table_id to indicate merge
    table_id = base.table_id
    if not table_id.endswith("_merged"):
        table_id = f"{table_id}_merged"

    return Table(
        table_id=table_id,
        page=base.page,
        title=base.title,
        cells=all_cells,
        n_rows=n_rows,
        n_cols=n_cols,
        raw_markdown=raw_md,
        source_refs=source_refs,
    )


def _cells_to_raw_rows(
    cells: list[TableCell], n_rows: int, n_cols: int
) -> list[list[str | None]]:
    """Reconstruct raw row-major data from a flat cell list."""
    grid: list[list[str | None]] = [[None] * n_cols for _ in range(n_rows)]
    for c in cells:
        if c.row < n_rows and c.col < n_cols:
            grid[c.row][c.col] = c.text or ""
    return grid


# ── Shared helpers ───────────────────────────────────────────────────────────


def _raw_to_table(
    raw_table: list[list[str | None]],
    *,
    page_index: int,
    table_index: int,
    engine_name: str,
    page_width: float,
    page_height: float,
    page_table_obj: object | None,
    camelot_accuracy: float | None = None,
) -> Table:
    """Convert a raw 2-D string grid into a :class:`Table` model."""
    cells: list[TableCell] = []
    n_rows = len(raw_table)
    n_cols = max((len(row) for row in raw_table), default=0)

    for r_idx, row in enumerate(raw_table):
        for c_idx, cell in enumerate(row):
            bbox = None
            if page_table_obj is not None:
                bbox = _cell_bbox(page_table_obj, r_idx, c_idx, page_width, page_height)
            cells.append(
                TableCell(
                    row=r_idx,
                    col=c_idx,
                    text=str(cell or "").strip(),
                    bbox=bbox,
                    engine=engine_name,
                )
            )

    table_id = f"p{page_index}_t{table_index}"
    confidence = (
        round(camelot_accuracy / 100.0, 2)
        if camelot_accuracy is not None
        else _score_table_confidence(raw_table)
    )
    title = _detect_table_title(raw_table)
    source = SourceRef(
        ref_type="table",
        page=page_index,
        table_id=table_id,
        bbox=(
            _normalize_bbox(page_table_obj.bbox, page_width, page_height)
            if page_table_obj is not None and hasattr(page_table_obj, "bbox")
            else None
        ),
        quote=None,
        confidence=confidence,
        engine=engine_name,
    )

    return Table(
        table_id=table_id,
        page=page_index,
        title=title,
        cells=cells,
        n_rows=n_rows,
        n_cols=n_cols,
        raw_markdown=_table_to_markdown(raw_table),
        source_refs=[source],
    )


def _cell_bbox(
    page_table: object,
    row_index: int,
    col_index: int,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float] | None:
    rows = getattr(page_table, "rows", [])
    if row_index >= len(rows):
        return None
    row = rows[row_index]
    cells = getattr(row, "cells", [])
    if col_index >= len(cells):
        return None
    return _normalize_bbox(cells[col_index], page_width, page_height)


def _normalize_bbox(
    bbox: tuple[float, float, float, float] | None,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float] | None:
    if bbox is None or page_width <= 0 or page_height <= 0:
        return None
    left, top, right, bottom = bbox
    if right <= left or bottom <= top:
        return None
    return (
        round(left / page_width, 6),
        round(top / page_height, 6),
        round(right / page_width, 6),
        round(bottom / page_height, 6),
    )


def _score_table_confidence(raw_table: list[list[str | None]]) -> float:
    """Score table confidence 0–1 based on numeric cell density.

    Financial statement tables have high proportions of numeric cells.
    Baseline is 0.55; scales up to 0.95 with denser numeric content.
    """
    if not raw_table:
        return 0.0
    total = 0
    numeric = 0
    for row in raw_table:
        for cell in row:
            if cell is not None:
                total += 1
                stripped = (
                    str(cell)
                    .strip()
                    .replace(",", "")
                    .replace(" ", "")
                    .lstrip("$¥￥€£＄△▲-－(（")
                    .rstrip(")）%％万元亿")
                )
                if stripped:
                    try:
                        float(stripped)
                        numeric += 1
                    except ValueError:
                        pass
    if total == 0:
        return 0.5
    ratio = numeric / total
    return round(min(0.55 + ratio * 0.4, 0.95), 2)


def _detect_table_title(raw_table: list[list[str | None]]) -> str | None:
    """Return a title string if the first row looks like a merged header."""
    if not raw_table:
        return None
    first_row = raw_table[0]
    non_empty = [str(c).strip() for c in first_row if c and str(c).strip()]
    if not non_empty:
        return None

    if len(non_empty) == 1 and len(non_empty[0]) > 2:
        return non_empty[0]

    _TITLE_KEYWORDS = [
        "资产负债表", "利润表", "现金流量表", "合并",
        "balance sheet", "income statement", "cash flow",
        "profit", "statement of",
    ]
    first_cell = non_empty[0].lower()
    if any(kw.lower() in first_cell for kw in _TITLE_KEYWORDS):
        return non_empty[0]

    return None


def is_header_row(row: Sequence[str | None]) -> bool:
    """Return True when *row* is likely a column-header row (mostly non-numeric)."""
    non_empty = [str(c).strip() for c in row if c and str(c).strip()]
    if not non_empty:
        return False
    numeric_count = 0
    for cell in non_empty:
        stripped = (
            cell.replace(",", "")
            .lstrip("$¥￥€£＄△▲-－(（")
            .rstrip(")）%％万元亿")
        )
        try:
            float(stripped)
            numeric_count += 1
        except ValueError:
            pass
    return numeric_count < len(non_empty) / 2


def _table_to_markdown(raw_table: list[list[str | None]]) -> str:
    if not raw_table:
        return ""
    max_cols = max(len(row) for row in raw_table)
    rows = [
        [str(cell or "").strip() for cell in row] + [""] * (max_cols - len(row))
        for row in raw_table
    ]
    header = rows[0]
    separator = ["---" for _ in header]
    md_rows = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in rows[1:]:
        md_rows.append("| " + " | ".join(row) + " |")
    return "\n".join(md_rows)
