from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_type: Literal["page_text", "table", "image"]
    page: int
    table_id: str | None = None
    quote: str | None = Field(default=None)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("quote")
    @classmethod
    def _trim_quote(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value[:200]


class DocumentMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    filename: str
    company: str | None = None
    period_end: date | None = None
    report_type: str | None = None
    language: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int
    text: str
    images: list[str] = Field(default_factory=list)


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    page_start: int
    page_end: int
    section: str | None = None
    text: str
    bbox: tuple[float, float, float, float] | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


class TableCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int
    col: int
    text: str


class Table(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str
    page: int
    title: str | None = None
    cells: list[TableCell]
    n_rows: int
    n_cols: int
    raw_markdown: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


class StatementLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_raw: str
    name_norm: str
    value_current: float | None = None
    value_prior: float | None = None
    unit: str | None = None
    currency: str | None = None
    notes: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


class FinancialStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement_type: Literal["income", "balance", "cashflow"]
    period_end: date | None = None
    period_start: date | None = None
    line_items: list[StatementLineItem] = Field(default_factory=list)
    totals: dict[str, float] = Field(default_factory=dict)
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)


class KeyNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_type: Literal[
        "accounting_policy",
        "audit_opinion",
        "related_party",
        "impairment",
        "contingency",
        "segment",
        "guidance",
        "other",
    ]
    summary: str
    source_refs: list[SourceRef] = Field(default_factory=list)


class RiskSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    category: Literal[
        "cash_vs_profit",
        "accruals",
        "one_offs",
        "audit_governance",
        "disclosure_inconsistency",
        "working_capital",
        "other",
    ]
    title: str
    severity: Literal["low", "medium", "high"]
    description: str
    metrics: dict[str, float | str] = Field(default_factory=dict)
    evidence: list[SourceRef] = Field(default_factory=list)


class TraderReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    executive_summary: str
    key_drivers: list[str]
    numbers_snapshot: dict[str, float]
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    notes: list[KeyNote] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class EventStudyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_date: date
    window: tuple[int, int]
    returns: dict[str, float] = Field(default_factory=dict)
    volatility: dict[str, float] = Field(default_factory=dict)
    volume: dict[str, float] = Field(default_factory=dict)
    data_source: str
