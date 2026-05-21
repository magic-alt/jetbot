from __future__ import annotations

from pathlib import Path
from typing import Iterable

from src.pdf.engine import get_pdf_engine


def page_count(pdf_path: str) -> int:
    return get_pdf_engine("pdfium").page_count(pdf_path)


def extract_pages(pdf_path: str, page_numbers: Iterable[int], out_path: str) -> str:
    """Write a new PDF containing the selected 1-based page numbers."""
    indices = _validate_page_numbers(pdf_path, page_numbers, allow_empty=False)
    _copy_pages(pdf_path, indices, out_path)
    return out_path


def delete_pages(pdf_path: str, page_numbers: Iterable[int], out_path: str) -> str:
    """Write a new PDF with the selected 1-based page numbers removed."""
    total = page_count(pdf_path)
    delete_indices = set(_validate_page_numbers(pdf_path, page_numbers, allow_empty=False))
    keep_indices = [idx for idx in range(total) if idx not in delete_indices]
    if not keep_indices:
        raise ValueError("delete_pages cannot remove every page")
    _copy_pages(pdf_path, keep_indices, out_path)
    return out_path


def reorder_pages(pdf_path: str, page_numbers: Iterable[int], out_path: str) -> str:
    """Write a new PDF with pages ordered by the supplied 1-based page list."""
    indices = _validate_page_numbers(pdf_path, page_numbers, allow_empty=False)
    if len(set(indices)) != len(indices):
        raise ValueError("reorder_pages does not allow duplicate page numbers")
    if len(indices) != page_count(pdf_path):
        raise ValueError("reorder_pages must include every page exactly once")
    _copy_pages(pdf_path, indices, out_path)
    return out_path


def rotate_pages(
    pdf_path: str,
    page_numbers: Iterable[int] | None,
    out_path: str,
    *,
    degrees: int = 90,
) -> str:
    """Write a new PDF with selected pages rotated clockwise by *degrees*."""
    if degrees not in {0, 90, 180, 270}:
        raise ValueError("degrees must be one of 0, 90, 180, 270")

    total = page_count(pdf_path)
    target_indices = (
        set(range(total))
        if page_numbers is None
        else set(_validate_page_numbers(pdf_path, page_numbers, allow_empty=False))
    )

    pdfium = _import_pdfium()
    output = _new_output_path(out_path)
    with pdfium.PdfDocument(pdf_path) as src:
        dest = pdfium.PdfDocument.new()
        try:
            dest.import_pages(src, pages=list(range(total)))
            for idx in target_indices:
                page = dest[idx]
                try:
                    page.set_rotation((page.get_rotation() + degrees) % 360)
                finally:
                    page.close()
            dest.save(str(output))
        finally:
            dest.close()
    return str(output)


def merge_pdfs(pdf_paths: Iterable[str], out_path: str) -> str:
    """Write a new PDF containing all pages from *pdf_paths* in order."""
    paths = [str(Path(path)) for path in pdf_paths]
    if not paths:
        raise ValueError("merge_pdfs requires at least one input PDF")

    pdfium = _import_pdfium()
    output = _new_output_path(out_path)
    dest = pdfium.PdfDocument.new()
    try:
        for path in paths:
            if page_count(path) < 1:
                continue
            with pdfium.PdfDocument(path) as src:
                dest.import_pages(src, pages=None)
        if len(dest) < 1:
            raise ValueError("merge_pdfs produced an empty PDF")
        dest.save(str(output))
    finally:
        dest.close()
    return str(output)


def _copy_pages(pdf_path: str, indices: list[int], out_path: str) -> None:
    pdfium = _import_pdfium()
    output = _new_output_path(out_path)
    with pdfium.PdfDocument(pdf_path) as src:
        dest = pdfium.PdfDocument.new()
        try:
            dest.import_pages(src, pages=indices)
            dest.save(str(output))
        finally:
            dest.close()


def _validate_page_numbers(
    pdf_path: str,
    page_numbers: Iterable[int],
    *,
    allow_empty: bool,
) -> list[int]:
    pages = list(page_numbers)
    if not pages and not allow_empty:
        raise ValueError("at least one page number is required")

    total = page_count(pdf_path)
    indices: list[int] = []
    for page in pages:
        if page < 1 or page > total:
            raise ValueError(f"page_number {page} is out of range (1..{total})")
        indices.append(page - 1)
    return indices


def _new_output_path(out_path: str) -> Path:
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _import_pdfium():
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - dependency not installed
        raise RuntimeError(
            "pypdfium2 is required for PDF operations: "
            "pip install financial-report-agent[pdfium]"
        ) from exc
    return pdfium
