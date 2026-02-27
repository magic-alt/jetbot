"""Tests for validators — balance equation failure, unit mismatch, gross profit check."""
from __future__ import annotations

from src.finance.validators import validate_statements
from src.schemas.models import FinancialStatement, StatementLineItem


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
