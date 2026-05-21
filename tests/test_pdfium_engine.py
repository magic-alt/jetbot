from __future__ import annotations

from pathlib import Path

import pytest


pdfium = pytest.importorskip("pypdfium2")


def _make_pdf(path: Path, pages: int = 1) -> None:
    import fitz

    doc = fitz.open()
    for idx in range(pages):
        page = doc.new_page(width=300, height=240)
        page.insert_text((36, 72), f"PDFium page {idx + 1}", fontsize=12)
    doc.save(str(path))
    doc.close()


def _page_texts(path: Path) -> list[str]:
    texts: list[str] = []
    with pdfium.PdfDocument(str(path)) as pdf:
        for idx in range(len(pdf)):
            page = pdf[idx]
            try:
                text_page = page.get_textpage()
                try:
                    texts.append(text_page.get_text_bounded())
                finally:
                    text_page.close()
            finally:
                page.close()
    return texts


def test_pdfium_engine_extracts_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.pdf.extractor import PDFExtractor

    monkeypatch.setenv("PDF_ENGINE", "pdfium")
    pdf_path = tmp_path / "sample.pdf"
    _make_pdf(pdf_path)

    result = PDFExtractor().extract(str(pdf_path))

    assert result.needs_ocr is False
    assert len(result.pages) == 1
    assert "PDFium page 1" in result.pages[0].text


def test_pdfium_engine_renders_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.pdf.render import render_page

    monkeypatch.setenv("PDF_ENGINE", "pdfium")
    pdf_path = tmp_path / "sample.pdf"
    _make_pdf(pdf_path)

    image_path = Path(render_page(str(pdf_path), 1, str(tmp_path / "pages"), dpi=72))

    assert image_path.exists()
    assert image_path.name == "page_0001.png"
    assert image_path.stat().st_size > 0


def test_pdf_engine_factory_rejects_unknown_engine() -> None:
    from src.pdf.engine import get_pdf_engine

    with pytest.raises(ValueError, match="Unsupported PDF_ENGINE"):
        get_pdf_engine("unknown")


class TestPdfiumOperations:
    def test_extract_pages_writes_selected_pages(self, tmp_path: Path) -> None:
        from src.pdf.operations import extract_pages, page_count

        source = tmp_path / "source.pdf"
        output = tmp_path / "extract.pdf"
        _make_pdf(source, pages=3)

        extract_pages(str(source), [1, 3], str(output))

        assert page_count(str(output)) == 2
        assert _page_texts(output) == ["PDFium page 1", "PDFium page 3"]

    def test_delete_pages_removes_selected_pages(self, tmp_path: Path) -> None:
        from src.pdf.operations import delete_pages, page_count

        source = tmp_path / "source.pdf"
        output = tmp_path / "delete.pdf"
        _make_pdf(source, pages=3)

        delete_pages(str(source), [2], str(output))

        assert page_count(str(output)) == 2
        assert _page_texts(output) == ["PDFium page 1", "PDFium page 3"]

    def test_reorder_pages_requires_all_pages_once(self, tmp_path: Path) -> None:
        from src.pdf.operations import reorder_pages

        source = tmp_path / "source.pdf"
        output = tmp_path / "reorder.pdf"
        _make_pdf(source, pages=3)

        reorder_pages(str(source), [3, 1, 2], str(output))

        assert _page_texts(output) == ["PDFium page 3", "PDFium page 1", "PDFium page 2"]

    def test_rotate_pages_sets_page_rotation(self, tmp_path: Path) -> None:
        from src.pdf.operations import rotate_pages

        source = tmp_path / "source.pdf"
        output = tmp_path / "rotate.pdf"
        _make_pdf(source, pages=2)

        rotate_pages(str(source), [2], str(output), degrees=90)

        with pdfium.PdfDocument(str(output)) as pdf:
            first = pdf[0]
            second = pdf[1]
            try:
                assert first.get_rotation() == 0
                assert second.get_rotation() == 90
            finally:
                first.close()
                second.close()

    def test_merge_pdfs_combines_inputs(self, tmp_path: Path) -> None:
        from src.pdf.operations import merge_pdfs, page_count

        left = tmp_path / "left.pdf"
        right = tmp_path / "right.pdf"
        output = tmp_path / "merged.pdf"
        _make_pdf(left, pages=1)
        _make_pdf(right, pages=2)

        merge_pdfs([str(left), str(right)], str(output))

        assert page_count(str(output)) == 3

    def test_invalid_page_number_raises_value_error(self, tmp_path: Path) -> None:
        from src.pdf.operations import extract_pages

        source = tmp_path / "source.pdf"
        _make_pdf(source, pages=1)

        with pytest.raises(ValueError, match="out of range"):
            extract_pages(str(source), [2], str(tmp_path / "bad.pdf"))
