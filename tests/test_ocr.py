"""Tests for OCR engine abstraction (src/pdf/ocr.py)."""
from __future__ import annotations

import pytest
from src.pdf.ocr import OCRResult, PaddleOCREngine, TesseractOCREngine, get_ocr_engine, run_ocr


class TestOCRResult:
    def test_default_bbox_and_confidence(self):
        result = OCRResult(text="hello")
        assert result.text == "hello"
        assert result.bbox == (0.0, 0.0, 0.0, 0.0)
        assert result.confidence == 1.0

    def test_custom_values(self):
        result = OCRResult(text="world", bbox=(10.0, 20.0, 50.0, 60.0), confidence=0.9)
        assert result.bbox == (10.0, 20.0, 50.0, 60.0)
        assert result.confidence == 0.9


class TestPaddleOCREngineMissing:
    def test_raises_runtime_error_when_not_installed(self, monkeypatch):
        """PaddleOCREngine must raise RuntimeError when paddleocr is absent."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "paddleocr":
                raise ImportError("paddleocr not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(RuntimeError, match="paddleocr is not installed"):
            PaddleOCREngine()


class TestTesseractOCREngineMissing:
    def test_raises_runtime_error_when_not_installed(self, monkeypatch):
        """TesseractOCREngine.recognize must raise RuntimeError when pytesseract absent."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("pytesseract", "PIL"):
                raise ImportError("not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        engine = TesseractOCREngine()
        with pytest.raises(RuntimeError, match="pytesseract and Pillow are required"):
            engine.recognize("dummy.png", "auto")


class TestGetOCREngine:
    def test_returns_none_when_no_backends(self, monkeypatch):
        """get_ocr_engine must return None when all backends are unavailable."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("paddleocr", "pytesseract", "PIL"):
                raise ImportError("not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = get_ocr_engine("auto")
        assert result is None

    def test_english_lang_skips_paddle(self, monkeypatch):
        """With lang='en', PaddleOCR should be skipped and Tesseract tried."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "paddleocr":
                pytest.fail("PaddleOCR should not be tried for English")
            if name in ("pytesseract", "PIL"):
                raise ImportError("not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = get_ocr_engine("en")
        assert result is None


class TestRunOCR:
    def test_empty_paths_returns_empty_string(self):
        assert run_ocr([]) == ""

    def test_no_engine_returns_empty_string(self, monkeypatch):
        """run_ocr returns '' when no OCR engine is available."""
        monkeypatch.setattr("src.pdf.ocr.get_ocr_engine", lambda lang: None)
        assert run_ocr(["fake_image.png"]) == ""

    def test_engine_exception_is_gracefully_handled(self, monkeypatch):
        """run_ocr catches per-image exceptions and returns whatever succeeded."""

        class BrokenEngine:
            def recognize(self, image_path: str, lang: str) -> list[OCRResult]:
                raise RuntimeError("OCR failed")

        monkeypatch.setattr("src.pdf.ocr.get_ocr_engine", lambda lang: BrokenEngine())
        # Should return "" without raising
        assert run_ocr(["fake.png", "also_fake.png"]) == ""

    def test_partial_success(self, monkeypatch):
        """run_ocr aggregates results from pages that succeed."""
        from src.pdf.ocr import OCRResult

        calls: list[str] = []

        class PartialEngine:
            def recognize(self, image_path: str, lang: str) -> list[OCRResult]:
                calls.append(image_path)
                if "bad" in image_path:
                    raise RuntimeError("bad page")
                return [OCRResult(text="good text")]

        monkeypatch.setattr("src.pdf.ocr.get_ocr_engine", lambda lang: PartialEngine())
        result = run_ocr(["bad_page.png", "good_page.png"])
        assert "good text" in result
        assert len(calls) == 2
