from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from src.schemas.models import Correction, FinancialFact, FinancialStatement, SourceRef, StatementLineItem


def facts_from_statements(doc_id: str, statements: dict[str, FinancialStatement]) -> list[FinancialFact]:
    facts: list[FinancialFact] = []
    seen: set[tuple[str, str]] = set()

    for statement_type, statement in statements.items():
        if statement.statement_type not in {"income", "balance", "cashflow"}:
            continue
        for item in statement.line_items:
            if item.value_current is None and not item.source_refs:
                continue
            fact = _fact_from_line_item(doc_id, statement, item)
            facts.append(fact)
            seen.add((statement.statement_type, item.name_norm))

        for concept, value in statement.totals.items():
            key = (statement.statement_type, concept)
            if key in seen:
                continue
            facts.append(
                _build_fact(
                    doc_id=doc_id,
                    statement=statement,
                    concept=concept,
                    label=concept,
                    value=value,
                    unit=None,
                    currency=None,
                    source_refs=[],
                    confidence=statement.extraction_confidence,
                    metadata={"source": "statement_totals"},
                )
            )
    return facts


def apply_corrections(facts: Iterable[FinancialFact], corrections: Iterable[Correction]) -> list[FinancialFact]:
    by_id = {fact.fact_id: fact for fact in facts}
    valid_fields = set(FinancialFact.model_fields)

    for correction in corrections:
        fact = by_id.get(correction.fact_id)
        if fact is None or correction.field_name not in valid_fields:
            continue
        by_id[correction.fact_id] = fact.model_copy(update={correction.field_name: correction.new_value})
    return list(by_id.values())


def _fact_from_line_item(
    doc_id: str,
    statement: FinancialStatement,
    item: StatementLineItem,
) -> FinancialFact:
    confidence = _evidence_confidence(item.source_refs, statement.extraction_confidence)
    return _build_fact(
        doc_id=doc_id,
        statement=statement,
        concept=item.name_norm,
        label=item.name_raw,
        value=item.value_current,
        unit=item.unit,
        currency=item.currency,
        source_refs=item.source_refs,
        confidence=confidence,
        metadata={"notes": item.notes} if item.notes else {},
    )


def _build_fact(
    *,
    doc_id: str,
    statement: FinancialStatement,
    concept: str,
    label: str,
    value: float | None,
    unit: str | None,
    currency: str | None,
    source_refs: list[SourceRef],
    confidence: float,
    metadata: dict[str, Any],
) -> FinancialFact:
    return FinancialFact(
        fact_id=_fact_id(doc_id, statement.statement_type, concept, statement.period_end, label),
        doc_id=doc_id,
        statement_type=statement.statement_type,
        concept=concept,
        label=label,
        value=value,
        unit=unit,
        scale=_infer_scale(unit),
        currency=currency,
        period_start=statement.period_start,
        period_end=statement.period_end,
        period_type="instant" if statement.statement_type == "balance" else "duration",
        source_refs=source_refs,
        confidence=confidence,
        extraction_engine=_evidence_engine(source_refs),
        metadata=metadata,
    )


def _fact_id(doc_id: str, statement_type: str, concept: str, period_end: object, label: str) -> str:
    raw = "|".join([doc_id, statement_type, concept, str(period_end or ""), label])
    return "fact_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _evidence_confidence(source_refs: list[SourceRef], fallback: float) -> float:
    if not source_refs:
        return fallback
    return max(ref.confidence for ref in source_refs)


def _evidence_engine(source_refs: list[SourceRef]) -> str | None:
    for ref in source_refs:
        if ref.engine:
            return ref.engine
    return None


def _infer_scale(unit: str | None) -> float | None:
    if not unit:
        return None
    normalized = unit.lower().replace(" ", "_")
    if "billion" in normalized or "十亿" in normalized:
        return 1_000_000_000.0
    if "million" in normalized or "百万" in normalized:
        return 1_000_000.0
    if "thousand" in normalized or "千" in normalized:
        return 1_000.0
    if "亿元" in normalized or normalized.endswith("亿"):
        return 100_000_000.0
    if "万元" in normalized or normalized.endswith("万"):
        return 10_000.0
    return None