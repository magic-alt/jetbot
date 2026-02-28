from __future__ import annotations

from src.schemas.models import SourceRef


def test_source_ref_quote_trim():
    ref = SourceRef(ref_type="page_text", page=1, table_id=None, quote="a" * 250, confidence=0.5)
    assert ref.quote is not None
    assert len(ref.quote) == 200
