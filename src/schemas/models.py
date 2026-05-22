from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_type: Literal["page_text", "table", "image"]
    page: int
    table_id: str | None = None
    row: int | None = None
    col: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    quote: str | None = Field(default=None)
    confidence: float = Field(ge=0.0, le=1.0)
    engine: str | None = None
    artifact_path: str | None = None

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
    ticker: str | None = None
    cik: str | None = None
    filing_type: str | None = None
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
    rowspan: int = Field(default=1, ge=1)
    colspan: int = Field(default=1, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    engine: str | None = None


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


class FinancialFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    doc_id: str
    company: str | None = None
    ticker: str | None = None
    cik: str | None = None
    filing_type: str | None = None
    statement_type: Literal["income", "balance", "cashflow", "note", "other"]
    concept: str
    label: str
    raw_label: str | None = None
    value: float | None = None
    unit: str | None = None
    scale: float | None = None
    currency: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    period_type: Literal["instant", "duration", "unknown"] = "unknown"
    source_refs: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_engine: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    doc_id: str
    stage: str
    engine: str
    status: Literal["succeeded", "failed", "skipped"]
    elapsed_ms: int | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correction_id: str
    doc_id: str
    fact_id: str
    field_name: str
    old_value: Any = None
    new_value: Any = None
    actor: str = "system"
    reason: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class FactValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["low", "medium", "high"] = "medium"
    message: str
    fact_ids: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    statement_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[FactValidationIssue] = Field(default_factory=list)
    checks: dict[str, bool | float | int | str] = Field(default_factory=dict)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)


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


class AgentCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    name: str
    description: str
    enabled: bool = True
    provider: str | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class ModelInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    task: str
    status: Literal["succeeded", "failed", "skipped"]
    elapsed_ms: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class AgentRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    doc_id: str
    node_name: str
    provider: str
    model: str
    status: Literal["succeeded", "failed", "skipped"]
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    elapsed_ms: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisContextSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: Literal["page_text", "table", "statement", "note", "risk_signal", "validation"]
    title: str | None = None
    text: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    tokens_estimate: int | None = None


class AnalysisContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    metadata: DocumentMeta
    statement_snapshot: dict[str, float] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    sources: list[AnalysisContextSource] = Field(default_factory=list)
    token_budget: int
    tokens_estimate: int
    created_at: datetime = Field(default_factory=_utc_now)


class AnalysisFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    category: str
    title: str
    severity: Literal["low", "medium", "high"]
    summary: str
    detail: str | None = None
    metrics: dict[str, float | str] = Field(default_factory=dict)
    evidence: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("evidence", mode="before")
    @classmethod
    def _drop_invalid_evidence(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        filtered: list[Any] = []
        for item in value:
            if isinstance(item, SourceRef):
                filtered.append(item)
            elif isinstance(item, dict) and item.get("page") is not None:
                filtered.append(item)
        return filtered


class DeepAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    provider: str
    model: str
    summary: str
    findings: list[AnalysisFinding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    invocations: list[ModelInvocation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
