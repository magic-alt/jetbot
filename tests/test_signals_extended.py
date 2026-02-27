"""Tests for signals — working capital, audit governance, disclosure issues."""
from __future__ import annotations

from src.finance.signals import generate_signals
from src.schemas.models import FinancialStatement, KeyNote, StatementLineItem


def _make_item(name_raw: str, name_norm: str, current: float, prior: float) -> StatementLineItem:
    return StatementLineItem(
        name_raw=name_raw,
        name_norm=name_norm,
        value_current=current,
        value_prior=prior,
        unit=None,
        currency=None,
        notes=None,
        source_refs=[],
    )


def test_working_capital_signal_triggered():
    """AR growth exceeding revenue growth by >20% should trigger working_capital signal."""
    balance = FinancialStatement(
        statement_type="balance",
        line_items=[
            _make_item("应收账款", "accounts_receivable", current=200.0, prior=100.0),  # 100% growth
        ],
        totals={},
        extraction_confidence=0.8,
        issues=[],
    )
    income = FinancialStatement(
        statement_type="income",
        line_items=[
            _make_item("营业收入", "revenue", current=110.0, prior=100.0),  # 10% growth
        ],
        totals={"net_income": 10.0},
        extraction_confidence=0.8,
        issues=[],
    )
    signals = generate_signals(
        {"balance": balance, "income": income},
        notes=[],
        validation_results={"issues": []},
        pages_text=["page text"],
    )
    assert any(s.category == "working_capital" for s in signals)


def test_audit_governance_signal():
    """Audit keywords in notes should trigger audit_governance signal."""
    signals = generate_signals(
        {},
        notes=[KeyNote(note_type="audit_opinion", summary="本报告包含保留意见", source_refs=[])],
        validation_results={"issues": []},
        pages_text=[],
    )
    assert any(s.category == "audit_governance" for s in signals)


def test_audit_governance_high_severity():
    """Non-强调事项 keywords should produce 'high' severity."""
    signals = generate_signals(
        {},
        notes=[KeyNote(note_type="audit_opinion", summary="审计报告出具了否定意见", source_refs=[])],
        validation_results={"issues": []},
        pages_text=[],
    )
    audit_signal = next((s for s in signals if s.category == "audit_governance"), None)
    assert audit_signal is not None
    assert audit_signal.severity == "high"


def test_audit_governance_emphasis_severity():
    """强调事项 should produce 'medium' severity."""
    signals = generate_signals(
        {},
        notes=[KeyNote(note_type="audit_opinion", summary="包含强调事项段落", source_refs=[])],
        validation_results={"issues": []},
        pages_text=[],
    )
    audit_signal = next((s for s in signals if s.category == "audit_governance"), None)
    assert audit_signal is not None
    assert audit_signal.severity == "medium"


def test_disclosure_inconsistency_signal():
    """Balance equation failure should trigger disclosure_inconsistency signal."""
    signals = generate_signals(
        {},
        notes=[],
        validation_results={"issues": ["balance_equation_failed"]},
        pages_text=["test"],
    )
    assert any(s.category == "disclosure_inconsistency" for s in signals)
