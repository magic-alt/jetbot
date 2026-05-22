from __future__ import annotations

from src.pdf.engine import get_pdf_engine


def render_pages(pdf_path: str, out_dir: str, *, dpi: int = 200) -> list[str]:
    """Render every page of a PDF as a PNG image.

    Uses the configured PDF engine for rendering.  ``dpi`` defaults to 200,
    which is sufficient for OCR.  Pass ``dpi=72`` for lightweight preview
    thumbnails.  The default engine is PyMuPDF; set ``PDF_ENGINE=pdfium`` to use
    pypdfium2/PDFium.

    Returns a list of absolute file paths (one per page) in page order.
    """
    return get_pdf_engine().render_pages(pdf_path, out_dir, dpi=dpi)


def render_page(pdf_path: str, page_number: int, out_dir: str, *, dpi: int = 200) -> str:
    """Render a single 1-based *page_number* of a PDF and return its file path."""
    return get_pdf_engine().render_page(pdf_path, page_number, out_dir, dpi=dpi)
