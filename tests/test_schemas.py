from __future__ import annotations

from src.schemas.models import DeepAnalysisResult, SourceRef


def test_source_ref_quote_trim():
    ref = SourceRef(ref_type="page_text", page=1, table_id=None, quote="a" * 250, confidence=0.5)
    assert ref.quote is not None
    assert len(ref.quote) == 200


def test_deep_analysis_drops_evidence_without_page():
    result = DeepAnalysisResult.model_validate(
        {
            "doc_id": "doc-1",
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "summary": "ok",
            "findings": [
                {
                    "finding_id": "f1",
                    "category": "overview",
                    "title": "Finding",
                    "severity": "low",
                    "summary": "summary",
                    "evidence": [
                        {"ref_type": "page_text", "page": None, "quote": "missing page", "confidence": 0.2},
                        {"ref_type": "page_text", "page": 1, "quote": "valid page", "confidence": 0.8},
                    ],
                    "confidence": 0.7,
                }
            ],
            "limitations": [],
            "invocations": [],
        }
    )

    assert len(result.findings[0].evidence) == 1
    assert result.findings[0].evidence[0].page == 1
