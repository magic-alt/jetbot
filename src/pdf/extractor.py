from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.schemas.models import Page


@dataclass
class PDFExtractionResult:
    pages: list[Page]
    needs_ocr: bool
    # 0-based indices of pages where text was too sparse; OCR should be applied
    ocr_page_indices: list[int] = field(default_factory=list)


# Minimum character threshold below which a page is treated as a scanned image
_MIN_TEXT_CHARS = 20


def _check_pdf_header(path: str) -> bool:
    """Return True if *path* starts with the ``%PDF`` magic bytes."""
    with open(path, "rb") as fh:
        return fh.read(4) == b"%PDF"


class PDFExtractor:
    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        try:
            import fitz  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover - dependency not installed
            raise RuntimeError("PyMuPDF is required for PDF extraction") from exc

        if pdf_path and not _check_pdf_header(pdf_path):
            raise ValueError(f"File does not appear to be a valid PDF: {pdf_path}")

        doc = fitz.open(pdf_path)
        pages: list[Page] = []
        needs_ocr = False
        ocr_page_indices: list[int] = []
        render_path = Path(render_dir) if render_dir else None
        if render_path:
            render_path.mkdir(parents=True, exist_ok=True)

        for idx in range(doc.page_count):
            page = doc.load_page(idx)
            text = page.get_text("text")
            images: list[str] = []
            if render_path:
                pix = page.get_pixmap()
                img_path = render_path / f"page_{idx + 1:04d}.png"
                pix.save(str(img_path))
                images.append(str(img_path))
            if len(text.strip()) < _MIN_TEXT_CHARS and page.get_images(full=True):
                needs_ocr = True
                ocr_page_indices.append(idx)
            pages.append(Page(page_number=idx + 1, text=text, images=images))

        return PDFExtractionResult(
            pages=pages,
            needs_ocr=needs_ocr,
            ocr_page_indices=ocr_page_indices,
        )


class FakePDFExtractor:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        pages = [Page(page_number=1, text=self._text, images=[])]
        return PDFExtractionResult(pages=pages, needs_ocr=False, ocr_page_indices=[])
