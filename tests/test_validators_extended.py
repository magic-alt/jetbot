"""Tests for validators — balance equation failure, unit mismatch, gross profit check."""
from __future__ import annotations

from src.finance.validators import validate_facts, validate_statements
from src.schemas.models import DocumentMeta, FinancialFact, FinancialStatement, SourceRef, StatementLineItem


def test_balance_equation_failure():
    """When assets != liabilities + equity, balance_equation_failed should appear."""
    balance = FinancialStatement(
        statement_type="balance",
        line_items=[],
        totals={"total_assets": 100.0, "total_liabilities": 40.0, "total_equity": 50.0},
        extraction_confidence=0.9,
        issues=[],
    )
    results = validate_statements({"balance": balance})
    assert "balance_equation_failed" in results["issues"]


def test_balance_missing_totals():
    """When totals keys are missing, balance_missing_totals should appear."""
    balance = FinancialStatement(
        statement_type="balance",
        line_items=[],
        totals={"total_assets": 100.0},
        extraction_confidence=0.9,
        issues=[],
    )
    results = validate_statements({"balance": balance})
    assert "balance_missing_totals" in results["issues"]


def test_unit_mismatch():
    """Mixed units should trigger unit_mismatch."""
    balance = FinancialStatement(
        statement_type="balance",
        line_items=[
            StatementLineItem(name_raw="a", name_norm="total_assets", value_current=100.0, value_prior=None, unit="万元", currency=None, notes=None, source_refs=[]),
            StatementLineItem(name_raw="b", name_norm="total_liabilities", value_current=40.0, value_prior=None, unit="元", currency=None, notes=None, source_refs=[]),
        ],
        totals={"total_assets": 100.0, "total_liabilities": 40.0, "total_equity": 60.0},
        extraction_confidence=0.9,
        issues=[],
    )
    results = validate_statements({"balance": balance})
    assert any(issue.startswith("unit_mismatch") for issue in results["issues"])


def test_gross_profit_mismatch():
    """revenue - COGS != gross_profit should trigger line_total_mismatch."""
    income = FinancialStatement(
        statement_type="income",
        line_items=[],
        totals={"revenue": 200.0, "cost_of_goods_sold": 80.0, "gross_profit": 50.0, "net_income": 30.0},
        extraction_confidence=0.9,
        issues=[],
    )
    results = validate_statements({"income": income})
    assert "line_total_mismatch:gross_profit" in results["issues"]


def test_profit_to_cfo_ratio_negative_income():
    """With negative net_income, ratio should still be computed (denominator uses abs)."""
    income = FinancialStatement(
        statement_type="income",
        line_items=[],
        totals={"net_income": -20.0, "revenue": 100.0, "gross_profit": 40.0},
        extraction_confidence=0.9,
        issues=[],
    )
    cashflow = FinancialStatement(
        statement_type="cashflow",
        line_items=[],
        totals={"operating_cf": 10.0},
        extraction_confidence=0.9,
        issues=[],
    )
    results = validate_statements({"income": income, "cashflow": cashflow})
    ratio = results["metrics"].get("profit_to_cfo_ratio")
    assert ratio is not None
    assert abs(ratio - 10.0 / 20.0) < 1e-9


def test_validate_facts_flags_missing_critical_fact_and_missing_source_ref():
    facts = [
        FinancialFact(
            fact_id="fact-1",
            doc_id="doc-1",
            statement_type="income",
            concept="revenue",
            label="Revenue",
            raw_label="Revenue",
            value=100.0,
            period_type="duration",
            confidence=0.8,
            source_refs=[SourceRef(ref_type="page_text", page=1, confidence=0.8)],
        ),
        FinancialFact(
            fact_id="fact-2",
            doc_id="doc-1",
            statement_type="income",
            concept="net_income",
            label="Net income",
            raw_label="Net income",
            value=20.0,
            period_type="duration",
            confidence=0.8,
            source_refs=[],
        ),
    ]

    result = validate_facts(DocumentMeta(doc_id="doc-1", filename="demo.pdf"), facts, {"income": FinancialStatement(statement_type="income")})

    assert result.checks["missing_critical_facts"] is False
    assert result.checks["critical_facts_have_source_refs"] is False
    assert any(issue.code == "missing_critical_facts" for issue in result.issues)
    assert any(issue.code == "missing_source_refs" for issue in result.issues)


def test_validate_facts_flags_duplicates_and_balance_equation_failure():
    facts = [
        FinancialFact(
            fact_id="fact-assets-a",
            doc_id="doc-1",
            statement_type="balance",
            concept="total_assets",
            label="Total assets",
            raw_label="Total assets",
            value=100.0,
            period_type="instant",
            period_end=None,
            confidence=0.8,
            source_refs=[SourceRef(ref_type="page_text", page=1, confidence=0.8)],
        ),
        FinancialFact(
            fact_id="fact-assets-b",
            doc_id="doc-1",
            statement_type="balance",
            concept="total_assets",
            label="Assets",
            raw_label="Assets",
            value=100.0,
            period_type="instant",
            period_end=None,
            confidence=0.8,
            source_refs=[SourceRef(ref_type="page_text", page=1, confidence=0.8)],
        ),
        FinancialFact(
            fact_id="fact-liabilities",
            doc_id="doc-1",
            statement_type="balance",
            concept="total_liabilities",
            label="Total liabilities",
            raw_label="Total liabilities",
            value=70.0,
            period_type="instant",
            confidence=0.8,
            source_refs=[SourceRef(ref_type="page_text", page=1, confidence=0.8)],
        ),
        FinancialFact(
            fact_id="fact-equity",
            doc_id="doc-1",
            statement_type="balance",
            concept="total_equity",
            label="Total equity",
            raw_label="Total equity",
            value=20.0,
            period_type="instant",
            confidence=0.8,
            source_refs=[SourceRef(ref_type="page_text", page=1, confidence=0.8)],
        ),
    ]

    result = validate_facts(DocumentMeta(doc_id="doc-1", filename="demo.pdf"), facts, {"balance": FinancialStatement(statement_type="balance")})

    assert result.checks["duplicate_concepts"] is False
    assert result.checks["balance_equation"] is False
    assert any(issue.code == "duplicate_concepts" for issue in result.issues)
    assert any(issue.code == "balance_equation_failed" for issue in result.issues)
