from __future__ import annotations

from pathlib import Path


def render_pages(pdf_path: str, out_dir: str, *, dpi: int = 200) -> list[str]:
    """Render every page of a PDF as a PNG image.

    Uses PyMuPDF (fitz) for rendering.  ``dpi`` defaults to 200, which is
    sufficient for OCR.  Pass ``dpi=72`` for lightweight preview thumbnails.

    Returns a list of absolute file paths (one per page) in page order.
    """
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required for page rendering: pip install PyMuPDF"
        ) from exc

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    zoom = dpi / 72.0  # PyMuPDF's native resolution is 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    doc = fitz.open(pdf_path)
    image_paths: list[str] = []
    for idx in range(doc.page_count):
        page = doc.load_page(idx)
        pix = page.get_pixmap(matrix=matrix)
        img_path = out_path / f"page_{idx + 1:04d}.png"
        pix.save(str(img_path))
        image_paths.append(str(img_path))

    return image_paths


def render_page(pdf_path: str, page_number: int, out_dir: str, *, dpi: int = 200) -> str:
    """Render a single 1-based *page_number* of a PDF and return its file path."""
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required for page rendering: pip install PyMuPDF"
        ) from exc

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    doc = fitz.open(pdf_path)
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
