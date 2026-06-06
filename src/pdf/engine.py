from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.schemas.models import Page


@dataclass
class PDFExtractionResult:
    pages: list[Page]
    needs_ocr: bool
    # 0-based indices of pages where text was too sparse; OCR should be applied
    ocr_page_indices: list[int] = field(default_factory=list)


# Minimum character threshold below which a page is treated as a scanned image.
_MIN_TEXT_CHARS = 20


def check_pdf_header(path: str) -> bool:
    """Return True if *path* starts with the ``%PDF`` magic bytes."""
    with open(path, "rb") as fh:
        return fh.read(4) == b"%PDF"


class PdfEngine(Protocol):
    name: str

    def page_count(self, pdf_path: str) -> int:
        ...

    def metadata(self, pdf_path: str) -> dict[str, str | int | float | None]:
        ...

    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        ...

    def render_pages(self, pdf_path: str, out_dir: str, *, dpi: int = 200) -> list[str]:
        ...

    def render_page(self, pdf_path: str, page_number: int, out_dir: str, *, dpi: int = 200) -> str:
        ...


class PyMuPDFEngine:
    name = "pymupdf"

    def page_count(self, pdf_path: str) -> int:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(pdf_path)
        try:
            return int(doc.page_count)
        finally:
            doc.close()

    def metadata(self, pdf_path: str) -> dict[str, str | int | float | None]:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(pdf_path)
        try:
            return {
                **{str(k): v for k, v in (doc.metadata or {}).items()},
                "page_count": int(doc.page_count),
                "engine": self.name,
            }
        finally:
            doc.close()

    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        import fitz  # type: ignore[import-untyped]

        _ensure_valid_pdf(pdf_path)

        doc = fitz.open(pdf_path)
        pages: list[Page] = []
        needs_ocr = False
        ocr_page_indices: list[int] = []
        render_path = _ensure_render_dir(render_dir)

        try:
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
        finally:
            doc.close()

        return PDFExtractionResult(
            pages=pages,
            needs_ocr=needs_ocr,
            ocr_page_indices=ocr_page_indices,
        )

    def render_pages(self, pdf_path: str, out_dir: str, *, dpi: int = 200) -> list[str]:
        import fitz  # type: ignore[import-untyped]

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        doc = fitz.open(pdf_path)
        image_paths: list[str] = []
        try:
            for idx in range(doc.page_count):
                page = doc.load_page(idx)
                pix = page.get_pixmap(matrix=matrix)
                img_path = out_path / f"page_{idx + 1:04d}.png"
                pix.save(str(img_path))
                image_paths.append(str(img_path))
        finally:
            doc.close()

        return image_paths

    def render_page(self, pdf_path: str, page_number: int, out_dir: str, *, dpi: int = 200) -> str:
        import fitz  # type: ignore[import-untyped]

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        doc = fitz.open(pdf_path)
        try:
            idx = page_number - 1
            if idx < 0 or idx >= doc.page_count:
                raise ValueError(
                    f"page_number {page_number} is out of range (1..{doc.page_count})"
                )

            page = doc.load_page(idx)
            pix = page.get_pixmap(matrix=matrix)
            img_path = out_path / f"page_{page_number:04d}.png"
            pix.save(str(img_path))
            return str(img_path)
        finally:
            doc.close()


class PdfiumEngine:
    name = "pdfium"

    def page_count(self, pdf_path: str) -> int:
        pdfium = _import_pdfium()

        with pdfium.PdfDocument(pdf_path) as pdf:
            return len(pdf)

    def metadata(self, pdf_path: str) -> dict[str, str | int | float | None]:
        pdfium = _import_pdfium()

        with pdfium.PdfDocument(pdf_path) as pdf:
            return {
                "page_count": len(pdf),
                "version": pdf.get_version(),
                "engine": self.name,
            }

    def extract(self, pdf_path: str, render_dir: str | None = None) -> PDFExtractionResult:
        pdfium = _import_pdfium()

        _ensure_valid_pdf(pdf_path)

        pages: list[Page] = []
        needs_ocr = False
        ocr_page_indices: list[int] = []
        render_path = _ensure_render_dir(render_dir)

        with pdfium.PdfDocument(pdf_path) as pdf:
            for idx in range(len(pdf)):
                page = pdf[idx]
                try:
                    text = self._extract_page_text(page)
                    images: list[str] = []
                    if render_path:
                        img_path = render_path / f"page_{idx + 1:04d}.png"
                        self._save_page_bitmap(page, img_path, dpi=200)
                        images.append(str(img_path))
                    if len(text.strip()) < _MIN_TEXT_CHARS and self._page_has_images(page):
                        needs_ocr = True
                        ocr_page_indices.append(idx)
                    pages.append(Page(page_number=idx + 1, text=text, images=images))
                finally:
                    page.close()

        return PDFExtractionResult(
            pages=pages,
            needs_ocr=needs_ocr,
            ocr_page_indices=ocr_page_indices,
        )

    def render_pages(self, pdf_path: str, out_dir: str, *, dpi: int = 200) -> list[str]:
        pdfium = _import_pdfium()

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        image_paths: list[str] = []
        with pdfium.PdfDocument(pdf_path) as pdf:
            for idx in range(len(pdf)):
                page = pdf[idx]
                try:
                    img_path = out_path / f"page_{idx + 1:04d}.png"
                    self._save_page_bitmap(page, img_path, dpi=dpi)
                    image_paths.append(str(img_path))
                finally:
                    page.close()
        return image_paths

    def render_page(self, pdf_path: str, page_number: int, out_dir: str, *, dpi: int = 200) -> str:
        pdfium = _import_pdfium()

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        with pdfium.PdfDocument(pdf_path) as pdf:
            idx = page_number - 1
            if idx < 0 or idx >= len(pdf):
                raise ValueError(f"page_number {page_number} is out of range (1..{len(pdf)})")

            page = pdf[idx]
            try:
                img_path = out_path / f"page_{page_number:04d}.png"
                self._save_page_bitmap(page, img_path, dpi=dpi)
                return str(img_path)
            finally:
                page.close()

    @staticmethod
    def _extract_page_text(page) -> str:
        text_page = page.get_textpage()
        try:
            return text_page.get_text_bounded().replace("\r\n", "\n")
        finally:
            text_page.close()

    @staticmethod
    def _save_page_bitmap(page, img_path: Path, *, dpi: int) -> None:
        bitmap = page.render(
            scale=dpi / 72.0,
            draw_annots=True,
            fill_color=(255, 255, 255, 255),
            optimize_mode="lcd",
        )
        try:
            bitmap.to_pil().save(str(img_path))
        finally:
            close = getattr(bitmap, "close", None)
            if close is not None:
                close()

    @staticmethod
    def _page_has_images(page) -> bool:
        try:
            import pypdfium2.raw as pdfium_c  # type: ignore[import-untyped]

            for _obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
                return True
        except Exception:
            return False
        return False


_engine_cache: dict[str, PdfEngine] = {}


def get_pdf_engine(name: str | None = None) -> PdfEngine:
    requested = (name or os.getenv("PDF_ENGINE") or "pymupdf").strip().lower()
    if requested in {"pymupdf", "fitz"}:
        requested = "pymupdf"
    elif requested in {"pdfium", "pypdfium2"}:
        requested = "pdfium"
    else:
        raise ValueError(f"Unsupported PDF_ENGINE {requested!r}. Use 'pymupdf' or 'pdfium'.")

    if requested not in _engine_cache:
        if requested == "pymupdf":
            _engine_cache[requested] = PyMuPDFEngine()
        else:
            _engine_cache[requested] = PdfiumEngine()
    return _engine_cache[requested]


def _ensure_valid_pdf(pdf_path: str) -> None:
    if pdf_path and not check_pdf_header(pdf_path):
        raise ValueError(f"File does not appear to be a valid PDF: {pdf_path}")


def _ensure_render_dir(render_dir: str | None) -> Path | None:
    render_path = Path(render_dir) if render_dir else None
    if render_path:
        render_path.mkdir(parents=True, exist_ok=True)
    return render_path


def _import_pdfium():
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - dependency not installed
        raise RuntimeError(
            "pypdfium2 is required for PDFium support: "
            "pip install financial-report-agent[pdfium]"
        ) from exc
    return pdfium
