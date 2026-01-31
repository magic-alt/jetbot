from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.schemas.models import Page


@dataclass
class PDFExtractionResult:
    pages: list[Page]
    needs_ocr: bool


class PDFExtractor:
    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        try:
            import fitz
        except Exception as exc:  # pragma: no cover - dependency not installed
            raise RuntimeError("PyMuPDF is required for PDF extraction") from exc

        doc = fitz.open(pdf_path)
        pages: list[Page] = []
        needs_ocr = False
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
            if len(text.strip()) < 20 and page.get_images(full=True):
                needs_ocr = True
            pages.append(Page(page_number=idx + 1, text=text, images=images))
        return PDFExtractionResult(pages=pages, needs_ocr=needs_ocr)


class FakePDFExtractor:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        pages = [Page(page_number=1, text=self._text, images=[])]
        return PDFExtractionResult(pages=pages, needs_ocr=False)
