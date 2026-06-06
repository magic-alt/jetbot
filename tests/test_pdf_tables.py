from __future__ import annotations

from src.pdf.tables import _cell_bbox, _normalize_bbox


class _Row:
    def __init__(self, cells: list[tuple[float, float, float, float] | None]) -> None:
        self.cells = cells


class _Table:
    def __init__(self) -> None:
        self.rows = [_Row([(10.0, 20.0, 30.0, 60.0), None])]


def test_normalize_bbox_returns_page_relative_coordinates() -> None:
    bbox = _normalize_bbox((10.0, 20.0, 30.0, 60.0), page_width=100.0, page_height=200.0)

    assert bbox == (0.1, 0.1, 0.3, 0.3)


def test_cell_bbox_reads_pdfplumber_table_cells() -> None:
    table = _Table()

    assert _cell_bbox(table, 0, 0, page_width=100.0, page_height=200.0) == (0.1, 0.1, 0.3, 0.3)
    assert _cell_bbox(table, 0, 1, page_width=100.0, page_height=200.0) is None
