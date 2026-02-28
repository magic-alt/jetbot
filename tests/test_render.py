"""Tests for PDF page rendering (src/pdf/render.py)."""
from __future__ import annotations

from pathlib import Path

import pytest


def _make_minimal_pdf(path: Path) -> None:
    """Create a minimal single-page PDF at *path* using PyMuPDF."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text((72, 72), "Test page content", fontsize=12)
    doc.save(str(path))
    doc.close()


class TestRenderPages:
    def test_returns_one_path_per_page(self, tmp_path):
        """render_pages should produce one PNG file per page."""
        from src.pdf.render import render_pages

        pdf_path = tmp_path / "test.pdf"
        _make_minimal_pdf(pdf_path)

        out_dir = tmp_path / "renders"
        paths = render_pages(str(pdf_path), str(out_dir))

        assert len(paths) == 1
        assert all(Path(p).exists() for p in paths)
        assert Path(paths[0]).name == "page_0001.png"

    def test_creates_output_directory(self, tmp_path):
        """render_pages should create the output directory if it doesn't exist."""
        from src.pdf.render import render_pages

        pdf_path = tmp_path / "test.pdf"
        _make_minimal_pdf(pdf_path)

        new_dir = tmp_path / "new" / "nested" / "dir"
        assert not new_dir.exists()
        render_pages(str(pdf_path), str(new_dir))
        assert new_dir.exists()

    def test_dpi_parameter_affects_file_size(self, tmp_path):
        """Higher DPI should produce larger PNG files."""
        from src.pdf.render import render_pages

        pdf_path = tmp_path / "test.pdf"
        _make_minimal_pdf(pdf_path)

        low_paths = render_pages(str(pdf_path), str(tmp_path / "low"), dpi=72)
        high_paths = render_pages(str(pdf_path), str(tmp_path / "high"), dpi=200)

        low_size = Path(low_paths[0]).stat().st_size
        high_size = Path(high_paths[0]).stat().st_size
        assert high_size > low_size


class TestRenderPage:
    def test_single_page_renders_correctly(self, tmp_path):
        """render_page should render exactly one page and return its path."""
        from src.pdf.render import render_page

        pdf_path = tmp_path / "test.pdf"
        _make_minimal_pdf(pdf_path)

        img_path = render_page(str(pdf_path), page_number=1, out_dir=str(tmp_path))
        assert Path(img_path).exists()
        assert Path(img_path).name == "page_0001.png"

    def test_out_of_range_page_raises_value_error(self, tmp_path):
        """render_page must raise ValueError for an invalid page number."""
        from src.pdf.render import render_page

        pdf_path = tmp_path / "test.pdf"
        _make_minimal_pdf(pdf_path)

        with pytest.raises(ValueError, match="out of range"):
            render_page(str(pdf_path), page_number=99, out_dir=str(tmp_path))

    def test_zero_page_number_raises_value_error(self, tmp_path):
        """Page numbers are 1-based; 0 must raise ValueError."""
        from src.pdf.render import render_page

        pdf_path = tmp_path / "test.pdf"
        _make_minimal_pdf(pdf_path)

        with pytest.raises(ValueError, match="out of range"):
            render_page(str(pdf_path), page_number=0, out_dir=str(tmp_path))

    def test_negative_page_number_raises_value_error(self, tmp_path):
        """Negative page numbers must raise ValueError."""
        from src.pdf.render import render_page

        pdf_path = tmp_path / "test.pdf"
        _make_minimal_pdf(pdf_path)

        with pytest.raises(ValueError, match="out of range"):
            render_page(str(pdf_path), page_number=-1, out_dir=str(tmp_path))
