from __future__ import annotations

from pathlib import Path

from src.schemas.models import SourceRef, Table, TableCell


def extract_tables(pdf_path: str) -> list[Table]:
    try:
        import pdfplumber
    except Exception as exc:  # pragma: no cover - dependency not installed
        raise RuntimeError("pdfplumber is required for table extraction") from exc

    tables: list[Table] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables() or []
            for table_index, raw_table in enumerate(page_tables, start=1):
                cells: list[TableCell] = []
                n_rows = len(raw_table)
                n_cols = max((len(row) for row in raw_table), default=0)
                for r_idx, row in enumerate(raw_table):
                    for c_idx, cell in enumerate(row):
                        cells.append(TableCell(row=r_idx, col=c_idx, text=str(cell or "").strip()))
                table_id = f"p{page_index}_t{table_index}"
                source = SourceRef(
                    ref_type="table",
                    page=page_index,
                    table_id=table_id,
                    quote=None,
                    confidence=0.6,
                )
                tables.append(
                    Table(
                        table_id=table_id,
                        page=page_index,
                        title=None,
                        cells=cells,
                        n_rows=n_rows,
                        n_cols=n_cols,
                        raw_markdown=_table_to_markdown(raw_table),
                        source_refs=[source],
                    )
                )
    return tables


def _table_to_markdown(raw_table: list[list[str | None]]) -> str:
    if not raw_table:
        return ""
    rows = [[str(cell or "").strip() for cell in row] for row in raw_table]
    header = rows[0]
    separator = ["---" for _ in header]
    md_rows = ["| " + " | ".join(header) + " |", "| " + " | ".join(separator) + " |"]
    for row in rows[1:]:
        md_rows.append("| " + " | ".join(row) + " |")
    return "\n".join(md_rows)
