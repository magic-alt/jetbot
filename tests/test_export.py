"""Tests for the cross-project export module (schema + builder)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from src.export.schema import (
    CORE_METRICS,
    ExportedFact,
    ExportedFinancialFacts,
    ExportedRiskSignal,
)
from src.export.builder import (
    _compute_core_metrics,
    _convert_risk_signals,
    _derive_period_label,
    build_export,
)
from src.schemas.models import (
    DocumentMeta,
    FinancialFact,
    FinancialStatement,
    RiskSignal,
    SourceRef,
    StatementLineItem,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _source(page: int = 1, confidence: float = 0.9) -> SourceRef:
    return SourceRef(
        ref_type="table",
        page=page,
        table_id="p1_t1",
        row=1,
        col=1,
        confidence=confidence,
        engine="pdfplumber",
    )


def _item(
    name_raw: str,
    name_norm: str,
    value_current: float | None = None,
    value_prior: float | None = None,
    unit: str | None = "CNY",
    currency: str | None = "CNY",
    page: int = 1,
    confidence: float = 0.9,
) -> StatementLineItem:
    return StatementLineItem(
        name_raw=name_raw,
        name_norm=name_norm,
        value_current=value_current,
        value_prior=value_prior,
        unit=unit,
        currency=currency,
        source_refs=[_source(page, confidence)],
    )


def _meta(**overrides) -> DocumentMeta:
    defaults = dict(
        doc_id="doc-test-001",
        filename="annual_2025.pdf",
        company="Test Corp",
        ticker="600519.SH",
        filing_type="10-K",
        period_end=date(2025, 12, 31),
        language="zh",
    )
    defaults.update(overrides)
    return DocumentMeta(**defaults)


# ── Schema tests ─────────────────────────────────────────────────────────


class TestExportedFact:
    def test_minimal_fact(self) -> None:
        fact = ExportedFact(metric="revenue_growth", value=0.12, label="营收增长率")
        assert fact.metric == "revenue_growth"
        assert fact.value == 0.12
        assert fact.unit == "ratio"
        assert fact.confidence == 0.0

    def test_metric_normalised(self) -> None:
        fact = ExportedFact(metric=" Revenue_Growth ", value=0.1, label="x")
        assert fact.metric == "revenue_growth"

    def test_empty_metric_rejected(self) -> None:
        with pytest.raises(Exception):
            ExportedFact(metric="", value=0.1, label="x")

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):
            ExportedFact(metric="x", value=0.1, label="x", confidence=1.5)


class TestExportedFinancialFacts:
    def test_minimal_envelope(self) -> None:
        env = ExportedFinancialFacts(doc_id="abc")
        assert env.schema_version == "1.0"
        assert env.doc_id == "abc"
        assert env.facts == []
        assert env.risk_signals == []

    def test_deduplication_keeps_higher_confidence(self) -> None:
        facts = [
            ExportedFact(metric="gross_margin", value=0.30, label="毛利率", confidence=0.7),
            ExportedFact(metric="gross_margin", value=0.35, label="毛利率", confidence=0.9),
            ExportedFact(metric="debt_ratio", value=0.40, label="负债率", confidence=0.8),
        ]
        env = ExportedFinancialFacts(doc_id="x", facts=facts)
        assert len(env.facts) == 2
        gm = next(f for f in env.facts if f.metric == "gross_margin")
        assert gm.value == 0.35
        assert gm.confidence == 0.9


class TestExportedRiskSignal:
    def test_signal_creation(self) -> None:
        sig = ExportedRiskSignal(
            category="cash_vs_profit",
            title="Low cash conversion",
            severity="high",
            description="Operating cash flow is much lower than net profit.",
        )
        assert sig.severity == "high"
        assert sig.metrics == {}

    def test_invalid_severity_rejected(self) -> None:
        with pytest.raises(Exception):
            ExportedRiskSignal(
                category="other",
                title="t",
                severity="critical",  # type: ignore[arg-type]
                description="d",
            )


# ── Builder tests ────────────────────────────────────────────────────────


class TestDerivePeriodLabel:
    def test_annual_10k(self) -> None:
        meta = _meta(filing_type="10-K", period_end=date(2025, 12, 31))
        assert _derive_period_label(meta) == "2025Q4"

    def test_q1(self) -> None:
        meta = _meta(filing_type="Q1", period_end=date(2025, 3, 31))
        assert _derive_period_label(meta) == "2025Q1"

    def test_h1(self) -> None:
        meta = _meta(filing_type="H1", period_end=date(2025, 6, 30))
        assert _derive_period_label(meta) == "2025Q2"

    def test_no_period_end(self) -> None:
        meta = _meta(period_end=None)
        assert _derive_period_label(meta) is None


class TestComputeCoreMetrics:
    def _make_statements(
        self,
        income_items: list[StatementLineItem] | None = None,
        balance_items: list[StatementLineItem] | None = None,
        cashflow_items: list[StatementLineItem] | None = None,
    ) -> dict[str, FinancialStatement]:
        stmts: dict[str, FinancialStatement] = {}
        if income_items is not None:
            stmts["income"] = FinancialStatement(
                statement_type="income",
                line_items=income_items,
                extraction_confidence=0.85,
            )
        if balance_items is not None:
            stmts["balance"] = FinancialStatement(
                statement_type="balance",
                line_items=balance_items,
                extraction_confidence=0.80,
            )
        if cashflow_items is not None:
            stmts["cashflow"] = FinancialStatement(
                statement_type="cashflow",
                line_items=cashflow_items,
                extraction_confidence=0.75,
            )
        return stmts

    def test_revenue_growth(self) -> None:
        items = [
            _item("营业收入", "revenue", value_current=1500.0, value_prior=1200.0),
        ]
        stmts = self._make_statements(income_items=items)
        results = _compute_core_metrics(stmts, [])
        rev = next((f for f in results if f.metric == "revenue_growth"), None)
        assert rev is not None
        assert rev.value == pytest.approx(0.25, abs=1e-4)
        assert rev.label == "营收增长率"

    def test_net_profit_growth(self) -> None:
        items = [
            _item("净利润", "net_income", value_current=500.0, value_prior=400.0),
        ]
        stmts = self._make_statements(income_items=items)
        results = _compute_core_metrics(stmts, [])
        np_ = next((f for f in results if f.metric == "net_profit_growth"), None)
        assert np_ is not None
        assert np_.value == pytest.approx(0.25, abs=1e-4)

    def test_gross_margin_from_gross_profit(self) -> None:
        items = [
            _item("营业收入", "revenue", value_current=1000.0),
            _item("毛利润", "gross_profit", value_current=400.0),
        ]
        stmts = self._make_statements(income_items=items)
        results = _compute_core_metrics(stmts, [])
        gm = next((f for f in results if f.metric == "gross_margin"), None)
        assert gm is not None
        assert gm.value == pytest.approx(0.40, abs=1e-4)

    def test_gross_margin_fallback_revenue_minus_cogs(self) -> None:
        items = [
            _item("营业收入", "revenue", value_current=1000.0),
            _item("营业成本", "cost_of_revenue", value_current=600.0),
        ]
        stmts = self._make_statements(income_items=items)
        results = _compute_core_metrics(stmts, [])
        gm = next((f for f in results if f.metric == "gross_margin"), None)
        assert gm is not None
        assert gm.value == pytest.approx(0.40, abs=1e-4)

    def test_operating_cash_flow(self) -> None:
        items = [
            _item(
                "经营活动产生的现金流量净额",
                "net_cash_from_operating_activities",
                value_current=800_000_000.0,
            ),
        ]
        stmts = self._make_statements(cashflow_items=items)
        results = _compute_core_metrics(stmts, [])
        ocf = next((f for f in results if f.metric == "operating_cash_flow"), None)
        assert ocf is not None
        assert ocf.value == pytest.approx(800_000_000.0, abs=1.0)

    def test_debt_ratio(self) -> None:
        items = [
            _item("资产总计", "total_assets", value_current=5000.0),
            _item("负债合计", "total_liabilities", value_current=3000.0),
        ]
        stmts = self._make_statements(balance_items=items)
        results = _compute_core_metrics(stmts, [])
        dr = next((f for f in results if f.metric == "debt_ratio"), None)
        assert dr is not None
        assert dr.value == pytest.approx(0.60, abs=1e-4)

    def test_all_five_metrics_computed(self) -> None:
        income = [
            _item("营业收入", "revenue", value_current=1500.0, value_prior=1200.0),
            _item("净利润", "net_income", value_current=500.0, value_prior=400.0),
            _item("毛利润", "gross_profit", value_current=600.0),
        ]
        balance = [
            _item("资产总计", "total_assets", value_current=5000.0),
            _item("负债合计", "total_liabilities", value_current=3000.0),
        ]
        cashflow = [
            _item(
                "经营活动产生的现金流量净额",
                "net_cash_from_operating_activities",
                value_current=800.0,
            ),
        ]
        stmts = self._make_statements(income, balance, cashflow)
        results = _compute_core_metrics(stmts, [])
        metrics = {f.metric for f in results}
        assert metrics == set(CORE_METRICS)

    def test_missing_statement_yields_no_metric(self) -> None:
        results = _compute_core_metrics({}, [])
        assert results == []

    def test_zero_prior_revenue_skips_growth(self) -> None:
        items = [
            _item("营业收入", "revenue", value_current=100.0, value_prior=0.0),
        ]
        stmts = self._make_statements(income_items=items)
        results = _compute_core_metrics(stmts, [])
        rev = next((f for f in results if f.metric == "revenue_growth"), None)
        assert rev is None


class TestConvertRiskSignals:
    def test_converts_empty_list(self) -> None:
        assert _convert_risk_signals([]) == []

    def test_converts_single_signal(self) -> None:
        sig = RiskSignal(
            signal_id="rs-1",
            category="cash_vs_profit",
            title="Low cash",
            severity="medium",
            description="Cash flow is low.",
            metrics={"ocf_ratio": 0.3},
        )
        results = _convert_risk_signals([sig])
        assert len(results) == 1
        assert results[0].category == "cash_vs_profit"
        assert results[0].severity == "medium"
        assert results[0].metrics == {"ocf_ratio": 0.3}


# ── End-to-end build_export test ─────────────────────────────────────────


class TestBuildExport:
    def test_full_build(self) -> None:
        meta = _meta()
        income = FinancialStatement(
            statement_type="income",
            line_items=[
                _item("营业收入", "revenue", value_current=1500.0, value_prior=1200.0),
                _item("净利润", "net_income", value_current=500.0, value_prior=400.0),
                _item("毛利润", "gross_profit", value_current=600.0),
            ],
            extraction_confidence=0.85,
        )
        balance = FinancialStatement(
            statement_type="balance",
            line_items=[
                _item("资产总计", "total_assets", value_current=5000.0),
                _item("负债合计", "total_liabilities", value_current=3000.0),
            ],
            extraction_confidence=0.80,
        )
        cashflow = FinancialStatement(
            statement_type="cashflow",
            line_items=[
                _item(
                    "经营活动产生的现金流量净额",
                    "net_cash_from_operating_activities",
                    value_current=800.0,
                ),
            ],
            extraction_confidence=0.75,
        )

        risk = RiskSignal(
            signal_id="rs-1",
            category="cash_vs_profit",
            title="Cash gap",
            severity="low",
            description="Minor gap.",
        )

        envelope = build_export(
            meta=meta,
            statements={"income": income, "balance": balance, "cashflow": cashflow},
            facts=[],
            risk_signals=[risk],
            corrections_applied=True,
        )

        assert envelope.schema_version == "1.0"
        assert envelope.symbol == "600519.SH"
        assert envelope.company == "Test Corp"
        assert envelope.period == "2025Q4"
        assert envelope.period_end == date(2025, 12, 31)
        assert envelope.doc_id == "doc-test-001"
        assert len(envelope.facts) == 5
        assert len(envelope.risk_signals) == 1
        assert envelope.metadata["corrections_applied"] is True

        # Verify serialisation roundtrip
        data = envelope.model_dump(mode="json")
        parsed = ExportedFinancialFacts.model_validate(data)
        assert parsed.doc_id == envelope.doc_id
        assert len(parsed.facts) == 5
