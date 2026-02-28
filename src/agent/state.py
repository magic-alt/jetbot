from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.models import (
    Chunk,
    DocumentMeta,
    EventStudyResult,
    FinancialStatement,
    KeyNote,
    Page,
    RiskSignal,
    Table,
    TraderReport,
)


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    doc_meta: DocumentMeta
    pages: list[Page] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    statements: dict[str, FinancialStatement] = Field(default_factory=dict)
    notes: list[KeyNote] = Field(default_factory=list)
    validation_results: dict[str, Any] = Field(default_factory=dict)
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    trader_report: TraderReport | None = None
    event_study_results: list[EventStudyResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)

    pdf_path: str | None = None
    data_dir: str | None = None
    retry_count: int = 0
    needs_ocr: bool = False
