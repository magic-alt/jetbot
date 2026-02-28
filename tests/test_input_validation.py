"""Tests for upload input validation helpers (src/api/routes.py)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


def _sanitize(name: str) -> str:
    from src.api.routes import _sanitize_filename
    return _sanitize_filename(name)


def _validate(content_type: str, first_bytes: bytes) -> None:
    from src.api.routes import _validate_pdf_bytes
    mock_file = MagicMock()
    mock_file.content_type = content_type
    _validate_pdf_bytes(mock_file, first_bytes)


_VALID_PDF_BYTES = b"%PDF-1.4 rest of header"


class TestSanitizeFilename:
    def test_normal_name_unchanged(self):
        assert _sanitize("report.pdf") == "report.pdf"

    def test_path_traversal_stripped(self):
        result = _sanitize("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_windows_path_stripped(self):
        result = _sanitize("C:\\Users\\evil\\file.pdf")
        assert "\\" not in result

    def test_special_chars_replaced(self):
        result = _sanitize("my report (Q3)!.pdf")
        assert "!" not in result
        assert "(" not in result
        assert ")" not in result

    def test_long_filename_truncated(self):
        long_name = "a" * 200 + ".pdf"
        result = _sanitize(long_name)
        assert len(result) <= 128

    def test_empty_name_returns_default(self):
        result = _sanitize("")
        assert result == "uploaded.pdf"

    def test_underscore_dash_dot_preserved(self):
        result = _sanitize("my_report-2025.v2.pdf")
        assert result == "my_report-2025.v2.pdf"


class TestValidatePdfBytes:
    def test_valid_pdf_passes(self):
        _validate("application/pdf", _VALID_PDF_BYTES)

    def test_valid_pdf_octet_stream_passes(self):
        _validate("application/octet-stream", _VALID_PDF_BYTES)

    def test_missing_content_type_with_valid_header_passes(self):
        _validate("", _VALID_PDF_BYTES)

    def test_wrong_magic_bytes_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate("application/pdf", b"NOTAPDF123")
        assert exc_info.value.status_code == 400

    def test_jpeg_content_type_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate("image/jpeg", _VALID_PDF_BYTES)
        assert exc_info.value.status_code == 400

    def test_short_bytes_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate("application/pdf", b"%PD")
        assert exc_info.value.status_code == 400

    def test_empty_bytes_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate("application/pdf", b"")
        assert exc_info.value.status_code == 400
