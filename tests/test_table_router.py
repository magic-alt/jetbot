"""Tests for the table extraction Protocol, Router, and cross-page merging."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.pdf.tables import (
    CamelotEngine,
    PdfplumberEngine,
    TableEngine,
    _avg_confidence,
    _is_continuation_at_page,
    extract_tables,
    is_header_row,
    merge_cross_page_tables,
)
from src.schemas.models import SourceRef, Table, TableCell


# ── Protocol satisfaction ────────────────────────────────────────────────────


class TestProtocolSatisfaction:
    """Verify engines satisfy the TableEngine Protocol."""

    def test_pdfplumber_satisfies_protocol(self) -> None:
        assert isinstance(PdfplumberEngine(), TableEngine)

    def test_camelot_satisfies_protocol(self) -> None:
        assert isinstance(CamelotEngine(), TableEngine)

    def test_pdfplumber_has_name(self) -> None:
        assert PdfplumberEngine().name == "pdfplumber"

    def test_camelot_has_name(self) -> None:
        assert CamelotEngine().name == "camelot"


# ── Router ───────────────────────────────────────────────────────────────────


class _FakeEngine:
    """Minimal engine for testing the router."""

    name = "fake"

    def __init__(self, tables: list[Table]) -> None:
        self._tables = tables

    def extract(self, pdf_path: str) -> list[Table]:
        return self._tables


def _make_table(
    table_id: str = "p1_t1",
    page: int = 1,
    n_rows: int = 3,
    n_cols: int = 2,
    title: str | None = None,
    confidence: float = 0.8,
) -> Table:
    cells = [
        TableCell(row=r, col=c, text=f"r{r}c{c}")
        for r in range(n_rows)
        for c in range(n_cols)
    ]
    return Table(
        table_id=table_id,
        page=page,
        title=title,
        cells=cells,
        n_rows=n_rows,
        n_cols=n_cols,
        raw_markdown="",
        source_refs=[
            SourceRef(ref_type="table", page=page, table_id=table_id, confidence=confidence)
        ],
    )


class TestRouter:
    """Test the extract_tables router function."""

    def test_auto_mode_uses_pdfplumber(self) -> None:
        fake_tables = [_make_table()]
        fake_engine = _FakeEngine(fake_tables)
        with patch("src.pdf.tables.PdfplumberEngine", return_value=fake_engine):
            result = extract_tables("/fake.pdf", engine="auto", merge_cross_page=False)
        assert len(result) == 1
        assert result[0].table_id == "p1_t1"

    def test_explicit_engine_selection(self) -> None:
        fake_tables = [_make_table()]
        fake_engine = _FakeEngine(fake_tables)
        with patch.dict("src.pdf.tables._ENGINES", {"camelot": lambda: fake_engine}):
            # Use the patched engine dict
            with patch("src.pdf.tables._extract_with_engine", return_value=fake_tables):
                result = extract_tables("/fake.pdf", engine="camelot", merge_cross_page=False)
        assert len(result) == 1

    def test_unknown_engine_falls_back_to_auto(self) -> None:
        fake_tables = [_make_table()]
        fake_engine = _FakeEngine(fake_tables)
        with patch("src.pdf.tables.PdfplumberEngine", return_value=fake_engine):
            result = extract_tables("/fake.pdf", engine="nonexistent", merge_cross_page=False)
        assert len(result) == 1

    def test_best_mode_picks_highest_confidence(self) -> None:
        plumber_tables = [_make_table(confidence=0.6)]
        camelot_tables = [_make_table(confidence=0.9)]

        plumber_engine = _FakeEngine(plumber_tables)
        camelot_engine = _FakeEngine(camelot_tables)

        with (
            patch("src.pdf.tables.PdfplumberEngine", return_value=plumber_engine),
            patch("src.pdf.tables.CamelotEngine", return_value=camelot_engine),
        ):
            result = extract_tables("/fake.pdf", engine="best", merge_cross_page=False)
        assert len(result) == 1
        assert result[0].source_refs[0].confidence == 0.9

    def test_env_var_engine_selection(self) -> None:
        fake_tables = [_make_table()]
        fake_engine = _FakeEngine(fake_tables)
        with (
            patch.dict("os.environ", {"TABLE_ENGINE": "auto"}),
            patch("src.pdf.tables.PdfplumberEngine", return_value=fake_engine),
        ):
            result = extract_tables("/fake.pdf", merge_cross_page=False)
        assert len(result) == 1

    def test_extraction_failure_returns_empty(self) -> None:
        class FailingEngine:
            name = "failing"

            def extract(self, pdf_path: str) -> list[Table]:
                raise RuntimeError("extraction failed")

        with patch("src.pdf.tables.PdfplumberEngine", return_value=FailingEngine()):
            result = extract_tables("/fake.pdf", merge_cross_page=False)
        assert result == []


# ── Cross-page merging ──────────────────────────────────────────────────────


class TestCrossPageMerging:
    """Test the cross-page table merging logic."""

    def test_no_merge_when_single_table(self) -> None:
        tables = [_make_table()]
        result = merge_cross_page_tables(tables)
        assert len(result) == 1

    def test_merge_consecutive_pages_same_cols(self) -> None:
        t1 = _make_table(table_id="p1_t1", page=1, n_rows=3, n_cols=2)
        t2 = _make_table(table_id="p2_t1", page=2, n_rows=2, n_cols=2)
        # t2 has no title and matching header → should merge (header skipped)
        result = merge_cross_page_tables([t1, t2])
        assert len(result) == 1
        assert result[0].n_rows == 4  # 3 + (2 - 1 skipped header)
        assert result[0].table_id == "p1_t1_merged"
        assert len(result[0].source_refs) == 2  # refs from both pages

    def test_no_merge_different_col_counts(self) -> None:
        t1 = _make_table(table_id="p1_t1", page=1, n_rows=3, n_cols=2)
        t2 = _make_table(table_id="p2_t1", page=2, n_rows=2, n_cols=4)
        result = merge_cross_page_tables([t1, t2])
        assert len(result) == 2

    def test_no_merge_when_continuation_has_title(self) -> None:
        t1 = _make_table(table_id="p1_t1", page=1, n_rows=3, n_cols=2)
        t2 = _make_table(table_id="p2_t1", page=2, n_rows=2, n_cols=2, title="New Table")
        result = merge_cross_page_tables([t1, t2])
        assert len(result) == 2

    def test_no_merge_non_consecutive_pages(self) -> None:
        t1 = _make_table(table_id="p1_t1", page=1, n_rows=3, n_cols=2)
        t2 = _make_table(table_id="p5_t1", page=5, n_rows=2, n_cols=2)
        result = merge_cross_page_tables([t1, t2])
        assert len(result) == 2

    def test_merge_three_pages(self) -> None:
        t1 = _make_table(table_id="p1_t1", page=1, n_rows=3, n_cols=2)
        t2 = _make_table(table_id="p2_t1", page=2, n_rows=2, n_cols=2)
        t3 = _make_table(table_id="p3_t1", page=3, n_rows=4, n_cols=2)
        result = merge_cross_page_tables([t1, t2, t3])
        assert len(result) == 1
        # 3 + (2-1) + (4-1) = 7 (each continuation skips its header row)
        assert result[0].n_rows == 7

    def test_merge_preserves_first_table_title(self) -> None:
        t1 = _make_table(table_id="p1_t1", page=1, n_rows=3, n_cols=2, title="Revenue")
        t2 = _make_table(table_id="p2_t1", page=2, n_rows=2, n_cols=2)
        result = merge_cross_page_tables([t1, t2])
        assert result[0].title == "Revenue"

    def test_mixed_tables_some_merged(self) -> None:
        t1 = _make_table(table_id="p1_t1", page=1, n_rows=3, n_cols=2)
        t2 = _make_table(table_id="p2_t1", page=2, n_rows=2, n_cols=2)
        t3 = _make_table(table_id="p3_t1", page=3, n_rows=4, n_cols=3, title="Different")
        result = merge_cross_page_tables([t1, t2, t3])
        assert len(result) == 2
        assert result[0].table_id == "p1_t1_merged"
        assert result[1].title == "Different"


# ── Continuation detection ───────────────────────────────────────────────────


class TestContinuationDetection:
    """Test the _is_continuation_at_page helper."""

    def test_basic_continuation(self) -> None:
        base = _make_table(page=1, n_cols=3)
        candidate = _make_table(page=2, n_cols=3)
        assert _is_continuation_at_page(base, candidate, expected_page=1) is True

    def test_not_continuation_wrong_page(self) -> None:
        base = _make_table(page=1, n_cols=3)
        candidate = _make_table(page=3, n_cols=3)
        assert _is_continuation_at_page(base, candidate, expected_page=1) is False

    def test_not_continuation_has_title(self) -> None:
        base = _make_table(page=1, n_cols=3)
        candidate = _make_table(page=2, n_cols=3, title="New Section")
        assert _is_continuation_at_page(base, candidate, expected_page=1) is False


# ── Header row detection ─────────────────────────────────────────────────────


class TestHeaderRowDetection:
    def test_header_row(self) -> None:
        assert is_header_row(["Name", "Description", "Value"]) is True

    def test_data_row(self) -> None:
        assert is_header_row(["100", "200", "300"]) is False

    def test_mixed_row(self) -> None:
        assert is_header_row(["Revenue", "100", "200"]) is False

    def test_empty_row(self) -> None:
        assert is_header_row(["", None, ""]) is False


# ── Average confidence ──────────────────────────────────────────────────────


class TestAvgConfidence:
    def test_empty_list(self) -> None:
        assert _avg_confidence([]) == 0.0

    def test_single_table(self) -> None:
        t = _make_table(confidence=0.8)
        assert _avg_confidence([t]) == pytest.approx(0.8)

    def test_multiple_tables(self) -> None:
        t1 = _make_table(confidence=0.6)
        t2 = _make_table(confidence=0.8)
        assert _avg_confidence([t1, t2]) == pytest.approx(0.7)
