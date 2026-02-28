from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class OCRResult:
    """A single text region detected by an OCR engine."""

    text: str
    bbox: tuple[float, float, float, float] = field(default=(0.0, 0.0, 0.0, 0.0))
    confidence: float = 1.0


@runtime_checkable
class OCREngine(Protocol):
    """Abstract OCR engine interface."""

    def recognize(self, image_path: str, lang: str) -> list[OCRResult]:
        """Recognise text in *image_path* and return structured results."""
        ...


class PaddleOCREngine:
    """PaddleOCR backend — best for Chinese + English mixed documents.

    Requires: ``pip install paddleocr paddlepaddle``
    """

    def __init__(self, lang: str = "ch") -> None:
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]

            self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        except ImportError as exc:
            raise RuntimeError(
                "paddleocr is not installed. Run: pip install paddleocr paddlepaddle"
            ) from exc

    def recognize(self, image_path: str, lang: str) -> list[OCRResult]:  # noqa: ARG002
        results = self._ocr.ocr(image_path, cls=True)
        items: list[OCRResult] = []
        if not results:
            return items
        for page_results in results:
            if not page_results:
                continue
            for line in page_results:
                if len(line) < 2:
                    continue
                coords, (text, confidence) = line[0], line[1]
                xs = [p[0] for p in coords]
                ys = [p[1] for p in coords]
                bbox = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
                items.append(OCRResult(text=str(text), bbox=bbox, confidence=float(confidence)))
        return items


class TesseractOCREngine:
    """Tesseract backend — primarily for English documents.

    Requires: ``pip install pytesseract Pillow`` **and** Tesseract installed on the OS.
    """

    def recognize(self, image_path: str, lang: str) -> list[OCRResult]:
        try:
            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "pytesseract and Pillow are required. Run: pip install pytesseract Pillow"
            ) from exc

        tess_lang = "chi_sim+chi_tra" if lang in ("zh", "cn", "ch") else "eng"
        img = Image.open(image_path)
        data = pytesseract.image_to_data(
            img, lang=tess_lang, output_type=pytesseract.Output.DICT
        )
        items: list[OCRResult] = []
        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            raw_conf = data["conf"][i]
            conf = float(raw_conf) / 100.0 if str(raw_conf) != "-1" else 0.5
            x, y, w, h = (
                data["left"][i],
                data["top"][i],
                data["width"][i],
                data["height"][i],
            )
            items.append(
                OCRResult(
                    text=text,
                    bbox=(float(x), float(y), float(x + w), float(y + h)),
                    confidence=conf,
                )
            )
        return items


def get_ocr_engine(lang: str = "auto") -> OCREngine | None:
    """Return the best available OCR engine for *lang*.

    Tries PaddleOCR first (better Chinese support), falls back to Tesseract,
    and returns ``None`` if neither is available.
    """
    if lang not in ("en", "eng"):
        try:
            return PaddleOCREngine(lang="ch" if lang in ("zh", "cn", "auto", "ch") else "en")
        except (RuntimeError, Exception):
            pass
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        return TesseractOCREngine()
    except (ImportError, RuntimeError, Exception):
        pass
    return None


def run_ocr(image_paths: list[str], lang: str = "auto") -> str:
    """Run OCR on a list of rendered page images and return combined text.

    Returns an empty string when no OCR engine is available or *image_paths* is empty.
    """
    if not image_paths:
        return ""
    engine = get_ocr_engine(lang)
    if engine is None:
        return ""
    parts: list[str] = []
    for img_path in image_paths:
        try:
            results = engine.recognize(img_path, lang=lang)
            page_text = " ".join(r.text for r in results if r.text)
            if page_text.strip():
                parts.append(page_text)
        except Exception:
            continue
    return "\n".join(parts)
