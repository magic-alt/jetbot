"""Pydantic models for the unified cross-project export envelope.

The export format is designed to be consumed by downstream quantitative
platforms (e.g. ``stock``) as fundamental-factor input.

Example payload::

    {
        "schema_version": "1.0",
        "symbol": "600519.SH",
        "company": "贵州茅台",
        "period": "2025Q4",
        "period_end": "2025-12-31",
        "source_document": "annual_report_2025.pdf",
        "doc_id": "doc_abc123",
        "generated_at": "2026-06-06T10:30:00+00:00",
        "facts": [
            {
                "metric": "revenue_growth",
                "value": 0.125,
                "unit": "ratio",
                "label": "营收增长率",
                "source_page": 42,
                "confidence": 0.96,
                "raw_value": 150555000000.0,
                "raw_unit": "CNY"
            }
        ],
        "risk_signals": [...],
        "metadata": {...}
    }
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Supported core metrics ──────────────────────────────────────────────
CORE_METRICS = (
    "revenue_growth",
    "net_profit_growth",
    "gross_margin",
    "operating_cash_flow",
    "debt_ratio",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExportedFact(BaseModel):
    """A single derived financial metric with evidence traceability."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(description="Standardised metric key (e.g. 'revenue_growth')")
    value: float = Field(description="Computed numeric value")
    unit: str = Field(default="ratio", description="Unit of value: ratio, CNY, USD, etc.")
    label: str = Field(description="Human-readable label (supports CJK)")
    source_page: int | None = Field(default=None, description="Best source page number")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_value: float | None = Field(default=None, description="Pre-computation raw value")
    raw_unit: str | None = Field(default=None, description="Unit of raw_value")
    computation: str | None = Field(
        default=None,
        description="Human-readable formula or note explaining how value was derived",
    )

    @field_validator("metric")
    @classmethod
    def _validate_metric(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("metric must not be empty")
        return v


class ExportedRiskSignal(BaseModel):
    """Lightweight risk signal for downstream consumption."""

    model_config = ConfigDict(extra="forbid")

    category: str
    title: str
    severity: Literal["low", "medium", "high"]
    description: str
    metrics: dict[str, float | str] = Field(default_factory=dict)


class ExportedFinancialFacts(BaseModel):
    """Top-level export envelope consumed by quantitative platforms."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    symbol: str | None = Field(default=None, description="Stock symbol (e.g. '600519.SH')")
    company: str | None = Field(default=None, description="Company name")
    period: str | None = Field(default=None, description="Reporting period (e.g. '2025Q4', '2025H1')")
    period_end: date | None = None
    source_document: str | None = Field(default=None, description="Original PDF filename")
    doc_id: str
    generated_at: datetime = Field(default_factory=_utc_now)
    facts: list[ExportedFact] = Field(default_factory=list)
    risk_signals: list[ExportedRiskSignal] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("facts")
    @classmethod
    def _deduplicate_metrics(cls, facts: list[ExportedFact]) -> list[ExportedFact]:
        seen: dict[str, int] = {}
        result: list[ExportedFact] = []
        for fact in facts:
            if fact.metric in seen:
                # Keep the higher-confidence entry
                idx = seen[fact.metric]
                if fact.confidence > result[idx].confidence:
                    result[idx] = fact
            else:
                seen[fact.metric] = len(result)
                result.append(fact)
        return result
