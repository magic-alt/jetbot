from __future__ import annotations

from datetime import date

from src.finance.facts import apply_corrections, facts_from_statements
from src.schemas.models import Correction, FinancialStatement, SourceRef, StatementLineItem


def test_facts_from_statements_preserves_line_item_evidence() -> None:
    source = SourceRef(
        ref_type="table",
        page=3,
        table_id="p3_t1",
        row=4,
        col=2,
        bbox=(10.0, 20.0, 30.0, 40.0),
        quote="Revenue 100",
        confidence=0.82,
        engine="pdfplumber",
    )
    statement = FinancialStatement(
        statement_type="income",
        period_end=date(2025, 12, 31),
        line_items=[
            StatementLineItem(
                name_raw="Revenue",
                name_norm="revenue",
                value_current=100.0,
                unit="USD millions",
                currency="USD",
                source_refs=[source],
            )
        ],
        totals={"revenue": 100.0},
        extraction_confidence=0.7,
    )

    facts = facts_from_statements("doc-1", {"income": statement})

    assert len(facts) == 1
    fact = facts[0]
    assert fact.doc_id == "doc-1"
    assert fact.statement_type == "income"
    assert fact.concept == "revenue"
    assert fact.value == 100.0
    assert fact.period_type == "duration"
    assert fact.scale == 1_000_000.0
    assert fact.confidence == 0.82
    assert fact.extraction_engine == "pdfplumber"
    assert fact.source_refs[0].bbox == (10.0, 20.0, 30.0, 40.0)


def test_facts_from_statements_adds_total_when_no_line_item_exists() -> None:
    statement = FinancialStatement(
        statement_type="balance",
        period_end=date(2025, 12, 31),
        totals={"total_assets": 500.0},
        extraction_confidence=0.6,
    )

    facts = facts_from_statements("doc-1", {"balance": statement})

    assert len(facts) == 1
    assert facts[0].concept == "total_assets"
    assert facts[0].period_type == "instant"
    assert facts[0].confidence == 0.6


def test_apply_corrections_updates_allowed_fact_field() -> None:
    statement = FinancialStatement(
        statement_type="income",
        line_items=[StatementLineItem(name_raw="Revenue", name_norm="revenue", value_current=100.0)],
    )
    fact = facts_from_statements("doc-1", {"income": statement})[0]
    correction = Correction(
        correction_id="c1",
        doc_id="doc-1",
        fact_id=fact.fact_id,
        field_name="value",
        old_value=100.0,
        new_value=125.0,
        actor="analyst",
    )

    corrected = apply_corrections([fact], [correction])

    assert corrected[0].value == 125.0
    assert fact.value == 100.0