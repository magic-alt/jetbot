"""Build an ``ExportedFinancialFacts`` envelope from jetbot internal models.

The builder reads raw ``FinancialFact`` objects, ``FinancialStatement`` line
items, and ``RiskSignal`` objects, then derives the five core metrics that
downstream quantitative platforms consume:

* ``revenue_growth``      – year-over-year revenue change ratio
* ``net_profit_growth``   – year-over-year net profit change ratio
* ``gross_margin``        – gross profit / revenue
* ``operating_cash_flow`` – net cash from operating activities (absolute)
* ``debt_ratio``          – total liabilities / total assets

Metrics that cannot be computed from the available data are silently omitted.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.export.schema import (
    ExportedFact,
    ExportedFinancialFacts,
    ExportedRiskSignal,
)
from src.schemas.models import (
    DocumentMeta,
    FinancialFact,
    FinancialStatement,
    RiskSignal,
    StatementLineItem,
)

logger = logging.getLogger(__name__)

# ── Normalised label aliases (English + Chinese) ──────────────────────────
_REVENUE_ALIASES = frozenset({
    "revenue", "total_revenue", "net_revenue", "sales",
    "营业收入", "营业总收入", "营业收入_净额",
})
_COGS_ALIASES = frozenset({
    "cost_of_revenue", "cost_of_goods_sold", "cogs", "cost_of_sales",
    "营业成本", "营业总成本",
})
_GROSS_PROFIT_ALIASES = frozenset({
    "gross_profit", "gross_margin_amount",
    "毛利润", "毛利",
})
_NET_PROFIT_ALIASES = frozenset({
    "net_income", "net_profit", "profit_for_the_period",
    "净利润", "归属于母公司所有者的净利润", "归母净利润",
})
_OPERATING_CASHFLOW_ALIASES = frozenset({
    "net_cash_from_operating_activities",
    "cash_flow_from_operations",
    "operating_cash_flow",
    "经营活动产生的现金流量净额",
    "经营活动现金流量净额",
})
_TOTAL_ASSETS_ALIASES = frozenset({
    "total_assets", "资产总计", "资产总额",
})
_TOTAL_LIABILITIES_ALIASES = frozenset({
    "total_liabilities", "负债合计", "负债总额",
})


def _normalise(label: str) -> str:
    return label.strip().lower().replace(" ", "_").replace("-", "_")


def _find_item_value(
    items: list[StatementLineItem],
    aliases: frozenset[str],
) -> tuple[float | None, StatementLineItem | None]:
    """Return (value, source_item) for the first matching line item."""
    for item in items:
        if _normalise(item.name_norm) in aliases or _normalise(item.name_raw) in aliases:
            if item.value_current is not None:
                return item.value_current, item
    return None, None


def _best_page(item: StatementLineItem | None) -> int | None:
    if item is None:
        return None
    for ref in item.source_refs:
        return ref.page
    return None


def _best_confidence(item: StatementLineItem | None, fallback: float = 0.0) -> float:
    if item is None:
        return fallback
    for ref in item.source_refs:
        return ref.confidence
    return fallback


def _derive_period_label(meta: DocumentMeta) -> str | None:
    """Infer a human-readable period label from document metadata."""
    if meta.period_end is None:
        return None
    year = meta.period_end.year
    month = meta.period_end.month
    filing = (meta.filing_type or meta.report_type or "").lower()
    if "q1" in filing or month == 3:
        return f"{year}Q1"
    if "q2" in filing or "h1" in filing or month == 6:
        return f"{year}Q2"
    if "q3" in filing or month == 9:
        return f"{year}Q3"
    if "q4" in filing or "annual" in filing or "10-k" in filing or month == 12:
        return f"{year}Q4"
    return f"{year}H1" if month <= 6 else f"{year}H2"


# ── Core metric computation ───────────────────────────────────────────────


def _compute_core_metrics(
    statements: dict[str, FinancialStatement],
    facts: list[FinancialFact],
) -> list[ExportedFact]:
    """Derive the five core metrics from statements and facts."""
    exported: list[ExportedFact] = []

    # Helper: get a statement by type
    income = statements.get("income")
    balance = statements.get("balance")
    cashflow = statements.get("cashflow")

    # ── 1. Revenue growth ─────────────────────────────────────────────
    if income is not None:
        rev_cur, rev_item = _find_item_value(income.line_items, _REVENUE_ALIASES)
        if rev_cur and rev_item and rev_item.value_prior is not None and rev_item.value_prior != 0:
            growth = (rev_cur - rev_item.value_prior) / abs(rev_item.value_prior)
            exported.append(ExportedFact(
                metric="revenue_growth",
                value=round(growth, 6),
                unit="ratio",
                label="营收增长率",
                source_page=_best_page(rev_item),
                confidence=_best_confidence(rev_item, income.extraction_confidence),
                raw_value=rev_cur,
                raw_unit=rev_item.unit or rev_item.currency,
                computation=f"(current={rev_cur} - prior={rev_item.value_prior}) / |prior|",
            ))

    # ── 2. Net profit growth ──────────────────────────────────────────
    if income is not None:
        np_cur, np_item = _find_item_value(income.line_items, _NET_PROFIT_ALIASES)
        if np_cur and np_item and np_item.value_prior is not None and np_item.value_prior != 0:
            growth = (np_cur - np_item.value_prior) / abs(np_item.value_prior)
            exported.append(ExportedFact(
                metric="net_profit_growth",
                value=round(growth, 6),
                unit="ratio",
                label="净利润增长率",
                source_page=_best_page(np_item),
                confidence=_best_confidence(np_item, income.extraction_confidence),
                raw_value=np_cur,
                raw_unit=np_item.unit or np_item.currency,
                computation=f"(current={np_cur} - prior={np_item.value_prior}) / |prior|",
            ))

    # ── 3. Gross margin ───────────────────────────────────────────────
    if income is not None:
        rev_val, rev_item = _find_item_value(income.line_items, _REVENUE_ALIASES)
        gp_val, gp_item = _find_item_value(income.line_items, _GROSS_PROFIT_ALIASES)
        # If gross profit not directly available, try revenue - COGS
        if gp_val is None and rev_val is not None:
            cogs_val, _ = _find_item_value(income.line_items, _COGS_ALIASES)
            if cogs_val is not None:
                gp_val = rev_val - cogs_val
                gp_item = rev_item  # use revenue item for source page
        if rev_val and gp_val and rev_val != 0:
            margin = gp_val / rev_val
            exported.append(ExportedFact(
                metric="gross_margin",
                value=round(margin, 6),
                unit="ratio",
                label="毛利率",
                source_page=_best_page(rev_item),
                confidence=_best_confidence(rev_item, income.extraction_confidence),
                raw_value=gp_val,
                raw_unit=rev_item.unit if rev_item else None,
                computation=f"gross_profit={gp_val} / revenue={rev_val}",
            ))

    # ── 4. Operating cash flow ────────────────────────────────────────
    if cashflow is not None:
        ocf_val, ocf_item = _find_item_value(cashflow.line_items, _OPERATING_CASHFLOW_ALIASES)
        if ocf_val is not None:
            exported.append(ExportedFact(
                metric="operating_cash_flow",
                value=round(ocf_val, 2),
                unit=ocf_item.unit or ocf_item.currency or "CNY" if ocf_item else "CNY",
                label="经营现金流",
                source_page=_best_page(ocf_item),
                confidence=_best_confidence(ocf_item, cashflow.extraction_confidence),
                raw_value=ocf_val,
                raw_unit=ocf_item.unit if ocf_item else None,
                computation="net_cash_from_operating_activities",
            ))

    # ── 5. Debt ratio ─────────────────────────────────────────────────
    if balance is not None:
        ta_val, ta_item = _find_item_value(balance.line_items, _TOTAL_ASSETS_ALIASES)
        tl_val, tl_item = _find_item_value(balance.line_items, _TOTAL_LIABILITIES_ALIASES)
        if ta_val and tl_val and ta_val != 0:
            ratio = tl_val / ta_val
            exported.append(ExportedFact(
                metric="debt_ratio",
                value=round(ratio, 6),
                unit="ratio",
                label="资产负债率",
                source_page=_best_page(tl_item) or _best_page(ta_item),
                confidence=_best_confidence(tl_item, balance.extraction_confidence),
                raw_value=tl_val,
                raw_unit=ta_item.unit if ta_item else None,
                computation=f"total_liabilities={tl_val} / total_assets={ta_val}",
            ))

    return exported


# ── Risk signal conversion ────────────────────────────────────────────────


def _convert_risk_signals(signals: list[RiskSignal]) -> list[ExportedRiskSignal]:
    """Convert internal RiskSignal objects to lightweight export format."""
    return [
        ExportedRiskSignal(
            category=s.category,
            title=s.title,
            severity=s.severity,
            description=s.description,
            metrics=s.metrics,
        )
        for s in signals
    ]


# ── Public API ────────────────────────────────────────────────────────────


def build_export(
    *,
    meta: DocumentMeta,
    statements: dict[str, FinancialStatement],
    facts: list[FinancialFact],
    risk_signals: list[RiskSignal] | None = None,
    corrections_applied: bool = False,
) -> ExportedFinancialFacts:
    """Build a normalised export envelope from jetbot internal models.

    Parameters
    ----------
    meta:
        Document metadata (ticker, company, period, etc.).
    statements:
        Keyed dict of ``FinancialStatement`` (income / balance / cashflow).
    facts:
        Flat list of ``FinancialFact`` (raw or effective).
    risk_signals:
        Optional list of ``RiskSignal`` to include.
    corrections_applied:
        Whether the facts include user corrections.

    Returns
    -------
    ExportedFinancialFacts
        The serialisable export envelope.
    """
    symbol = meta.ticker
    company = meta.company

    core_facts = _compute_core_metrics(statements, facts)
    exported_signals = _convert_risk_signals(risk_signals or [])

    return ExportedFinancialFacts(
        symbol=symbol,
        company=company,
        period=_derive_period_label(meta),
        period_end=meta.period_end,
        source_document=meta.filename,
        doc_id=meta.doc_id,
        generated_at=datetime.now(timezone.utc),
        facts=core_facts,
        risk_signals=exported_signals,
        metadata={
            "filing_type": meta.filing_type,
            "report_type": meta.report_type,
            "language": meta.language,
            "corrections_applied": corrections_applied,
            "total_raw_facts": len(facts),
        },
    )
