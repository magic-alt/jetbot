from __future__ import annotations


from src.schemas.models import SourceRef, Table, TableCell


def extract_tables(pdf_path: str) -> list[Table]:
    try:
        import pdfplumber  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - dependency not installed
        raise RuntimeError("pdfplumber is required for table extraction") from exc

    tables: list[Table] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            page_tables = page.find_tables() or []
            for table_index, page_table in enumerate(page_tables, start=1):
                raw_table = page_table.extract() or []
                if not raw_table:
                    continue
                cells: list[TableCell] = []
                n_rows = len(raw_table)
                n_cols = max((len(row) for row in raw_table), default=0)
                for r_idx, row in enumerate(raw_table):
                    for c_idx, cell in enumerate(row):
                        bbox = _cell_bbox(page_table, r_idx, c_idx, page.width, page.height)
                        cells.append(
                            TableCell(row=r_idx, col=c_idx, text=str(cell or "").strip(), bbox=bbox)
                        )
                table_id = f"p{page_index}_t{table_index}"
                confidence = _score_table_confidence(raw_table)
                title = _detect_table_title(raw_table)
                source = SourceRef(
                    ref_type="table",
                    page=page_index,
                    table_id=table_id,
                    bbox=_normalize_bbox(page_table.bbox, page.width, page.height),
                    quote=None,
                    confidence=confidence,
                )
                tables.append(
                    Table(
                        table_id=table_id,
                        page=page_index,
                        title=title,
                        cells=cells,
                        n_rows=n_rows,
                        n_cols=n_cols,
                        raw_markdown=_table_to_markdown(raw_table),
                        source_refs=[source],
                    )
                )
    return tables


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
    """Return a title string if the first row looks like a merged header.

    Heuristics:
    - First row has exactly one non-empty cell → treat as title.
    - First non-empty cell contains a known financial-statement keyword.
    """
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


def is_header_row(row: list[str | None]) -> bool:
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
