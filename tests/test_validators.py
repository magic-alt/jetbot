from __future__ import annotations

from src.finance.validators import validate_statements
from src.schemas.models import FinancialStatement, StatementLineItem


def test_validate_balance_equation():
    balance = FinancialStatement(
        statement_type="balance",
        line_items=[
            StatementLineItem(name_raw="????", name_norm="total_assets", value_current=100.0, value_prior=None, unit=None, currency=None, notes=None, source_refs=[]),
            StatementLineItem(name_raw="????", name_norm="total_liabilities", value_current=40.0, value_prior=None, unit=None, currency=None, notes=None, source_refs=[]),
            StatementLineItem(name_raw="???????", name_norm="total_equity", value_current=60.0, value_prior=None, unit=None, currency=None, notes=None, source_refs=[]),
        ],
        totals={"total_assets": 100.0, "total_liabilities": 40.0, "total_equity": 60.0},
        extraction_confidence=0.9,
        issues=[],
    )
    income = FinancialStatement(
        statement_type="income",
        line_items=[],
        totals={"net_income": 20.0, "revenue": 100.0, "gross_profit": 30.0},
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

    results = validate_statements({"balance": balance, "income": income, "cashflow": cashflow})
    assert "balance_equation_failed" not in results["issues"]
    assert results["metrics"]["profit_to_cfo_ratio"] == 0.5
