from __future__ import annotations

from src.schemas.models import FinancialStatement, SourceRef, StatementLineItem, Table


def find_total(statement: FinancialStatement, keys: list[str]) -> float | None:
    """Look up a total from statement.totals or fall back to line items."""
    for key in keys:
        if key in statement.totals:
            return statement.totals[key]
    for item in statement.line_items:
        if item.name_norm in keys and item.value_current is not None:
            return item.value_current
    return None


def find_line_item(statement: FinancialStatement, keywords: list[str]) -> StatementLineItem | None:
    """Find the first line item matching any of the given keywords."""
    for item in statement.line_items:
        name = f"{item.name_raw} {item.name_norm}".lower()
        for keyword in keywords:
            if keyword.lower() in name:
                return item
    return None


def fallback_evidence(pages_text: list[str]) -> list[SourceRef]:
    """Return minimal evidence from the first page when nothing better is available."""
    if pages_text:
        snippet = pages_text[0].strip().split("\n")[0][:200]
        return [SourceRef(ref_type="page_text", page=1, table_id=None, quote=snippet, confidence=0.2)]
    return [SourceRef(ref_type="page_text", page=1, table_id=None, quote="Evidence unavailable", confidence=0.1)]


def table_rows(table: Table) -> list[list[str]]:
    """Convert table cells into a list of rows (each row is a list of cell texts)."""
    if not table.cells:
        return []
    n_rows = table.n_rows or (max(c.row for c in table.cells) + 1)
    n_cols = table.n_cols or (max(c.col for c in table.cells) + 1)
    grid = [[""] * n_cols for _ in range(n_rows)]
    for cell in table.cells:
        if cell.row < n_rows and cell.col < n_cols:
            grid[cell.row][cell.col] = cell.text
    return grid


def table_to_text(table: Table) -> str:
    """Convert a Table into pipe-separated plain text."""
    ordered_rows = [" | ".join(row) for row in table_rows(table)]
    return "\n".join(ordered_rows)
