from __future__ import annotations

from src.finance.signals import generate_signals
from src.schemas.models import FinancialStatement, StatementLineItem, KeyNote


def test_generate_cash_vs_profit_signal():
    income = FinancialStatement(
        statement_type="income",
        line_items=[
            StatementLineItem(
                name_raw="净利润",
                name_norm="net_income",
                value_current=10.0,
                value_prior=None,
                unit=None,
                currency=None,
                notes=None,
                source_refs=[],
            )
        ],
        totals={"net_income": 10.0},
        extraction_confidence=0.8,
        issues=[],
    )
    cashflow = FinancialStatement(
        statement_type="cashflow",
        line_items=[
            StatementLineItem(
                name_raw="经营活动产生的现金流量净额",
                name_norm="operating_cf",
                value_current=-5.0,
                value_prior=None,
                unit=None,
                currency=None,
                notes=None,
                source_refs=[],
            )
        ],
        totals={"operating_cf": -5.0},
        extraction_confidence=0.8,
        issues=[],
    )

    signals = generate_signals(
        {"income": income, "cashflow": cashflow},
        notes=[KeyNote(note_type="other", summary="", source_refs=[])],
        validation_results={"issues": []},
        pages_text=["page text"],
    )
    assert any(signal.category == "cash_vs_profit" for signal in signals)
