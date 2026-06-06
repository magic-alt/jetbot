"""Pipeline node functions -- re-exported from sub-modules for backward compatibility."""
from __future__ import annotations

from src.agent.ingest_nodes import (
    detect_sections_and_chunk,
    extract_tables,
    ingest_pdf,
    _build_chunks_from_text,  # noqa: F401
    _split_text,  # noqa: F401
    _split_long_paragraph,  # noqa: F401
)
from src.agent.extraction_nodes import (
    extract_financial_statements,
    validate_and_reconcile,
    _detect_statement_type,  # noqa: F401
    _parse_number,  # noqa: F401
    _statement_from_pages,  # noqa: F401
)
from src.agent.analysis_nodes import (
    KeyNotesBundle,
    RiskSignalsBundle,
    build_analysis_context_node,
    extract_key_notes,
    generate_risk_signals,
    run_deep_analysis,
    _call_llm_parallel_structured,  # noqa: F401
    _call_llm_structured,  # noqa: F401
    _load_prompt,  # noqa: F401
)
from src.agent.report_nodes import (
    TraderReportDraft,
    build_trader_report,
    finalize,
    run_event_study_node,
    _render_markdown_report,  # noqa: F401
)

__all__ = [
    "KeyNotesBundle",
    "RiskSignalsBundle",
    "TraderReportDraft",
    "build_analysis_context_node",
    "build_trader_report",
    "detect_sections_and_chunk",
    "extract_financial_statements",
    "extract_key_notes",
    "extract_tables",
    "finalize",
    "generate_risk_signals",
    "ingest_pdf",
    "run_deep_analysis",
    "run_event_study_node",
    "validate_and_reconcile",
]
