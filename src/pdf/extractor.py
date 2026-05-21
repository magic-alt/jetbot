from __future__ import annotations

from src.pdf.engine import PDFExtractionResult, check_pdf_header, get_pdf_engine
from src.schemas.models import Page


class PDFExtractor:
    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        return get_pdf_engine().extract(pdf_path, render_dir=render_dir)


def _check_pdf_header(path: str) -> bool:
    """Backward-compatible wrapper for tests/imports."""
    return check_pdf_header(path)


class FakePDFExtractor:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        pages = [Page(page_number=1, text=self._text, images=[])]
        return PDFExtractionResult(pages=pages, needs_ocr=False, ocr_page_indices=[])
