from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.finance.utils import find_line_item, find_total
from src.schemas.models import DocumentMeta, FactValidationIssue, FactValidationResult, FinancialFact, FinancialStatement


_CRITICAL_FACTS: dict[str, tuple[str, ...]] = {
    "income": ("revenue", "gross_profit", "net_income"),
    "balance": ("total_assets", "total_liabilities", "total_equity"),
    "cashflow": ("operating_cash_flow", "capex"),
}

_CONCEPT_CANONICAL = {
    "operating_cf": "operating_cash_flow",
    "operating_cash_flow": "operating_cash_flow",
}


def _canonical_concept(concept: str) -> str:
    return _CONCEPT_CANONICAL.get(concept, concept)


def _fact_value(facts: list[FinancialFact], statement_type: str, concept: str) -> tuple[float | None, list[FinancialFact]]:
    matched = [
        fact
        for fact in facts
        if fact.statement_type == statement_type and _canonical_concept(fact.concept) == _canonical_concept(concept)
    ]
    for fact in matched:
        if fact.value is not None:
            return fact.value, matched
    return None, matched


def _unit_consistency(statement: FinancialStatement) -> list[str]:
    units = {item.unit for item in statement.line_items if item.unit}
    if len(units) > 1:
        return [f"unit_mismatch:{','.join(sorted(units))}"]
    return []


def _check_line_item_totals(statement: FinancialStatement) -> list[str]:
    """Check known additive relationships within statements.

    We only validate relationships we can reliably determine:
    - Balance: total_assets = total_liabilities + total_equity (handled separately)
    - Income: revenue - cost_of_goods_sold ≈ gross_profit (if all present)

    We do NOT attempt to sum all non-total items and compare against a total
    because financial statements have hierarchical subtotals (e.g. current
    assets subtotal, non-current assets subtotal, total assets) and naively
    summing all items would double-count subtotals.
    """
    issues: list[str] = []

    # Income statement: check revenue - COGS ≈ gross_profit if all available
    if statement.statement_type == "income":
        revenue = find_total(statement, ["revenue"])
        cogs = find_total(statement, ["cost_of_goods_sold"])
        gross_profit = find_total(statement, ["gross_profit"])
        if revenue is not None and cogs is not None and gross_profit is not None:
            expected = revenue - cogs
            if abs(expected - gross_profit) / max(abs(revenue), 1.0) > 0.05:
                issues.append("line_total_mismatch:gross_profit")

    return issues


def validate_statements(statements: dict[str, FinancialStatement], tolerance: float = 0.02) -> dict[str, Any]:
    results: dict[str, Any] = {"issues": [], "checks": {}, "metrics": {}}

    balance = statements.get("balance")
    if balance:
        total_assets = find_total(balance, ["total_assets"])
        total_liabilities = find_total(balance, ["total_liabilities"])
        total_equity = find_total(balance, ["total_equity"])
        if total_assets is not None and total_liabilities is not None and total_equity is not None:
            diff_ratio = abs(total_assets - (total_liabilities + total_equity)) / max(total_assets, 1.0)
            results["checks"]["balance_equation"] = diff_ratio
            if diff_ratio >= tolerance:
                results["issues"].append("balance_equation_failed")
        else:
            results["issues"].append("balance_missing_totals")
        results["issues"].extend(_unit_consistency(balance))
        results["issues"].extend(_check_line_item_totals(balance))

    income = statements.get("income")
    if income:
        required = ["revenue", "gross_profit", "net_income"]
        missing = [key for key in required if find_total(income, [key]) is None]
        if missing:
            results["issues"].append(f"income_missing:{','.join(missing)}")
        results["issues"].extend(_unit_consistency(income))
        results["issues"].extend(_check_line_item_totals(income))

    cashflow = statements.get("cashflow")
    if cashflow:
        results["issues"].extend(_unit_consistency(cashflow))
        results["issues"].extend(_check_line_item_totals(cashflow))

    net_income = find_total(income, ["net_income"]) if income else None
    operating_cf = find_total(cashflow, ["operating_cf"]) if cashflow else None
    if net_income is not None and operating_cf is not None:
        results["metrics"]["profit_to_cfo_ratio"] = operating_cf / max(abs(net_income), 1e-6)

    if balance and income:
        ar_item = find_line_item(balance, ["应收", "accounts receivable"])
        rev_item = find_line_item(income, ["营业收入", "revenue"])
        if ar_item and rev_item and ar_item.value_current is not None and ar_item.value_prior is not None:
            if rev_item.value_current is not None and rev_item.value_prior is not None:
                ar_growth = (ar_item.value_current - ar_item.value_prior) / max(abs(ar_item.value_prior), 1.0)
                rev_growth = (rev_item.value_current - rev_item.value_prior) / max(abs(rev_item.value_prior), 1.0)
                results["metrics"]["ar_growth_vs_rev_growth"] = ar_growth - rev_growth
    return results


def validate_facts(
    doc_meta: DocumentMeta,
    facts: list[FinancialFact],
    statements: dict[str, FinancialStatement] | None = None,
    tolerance: float = 0.02,
) -> FactValidationResult:
    result = FactValidationResult()
    statements = statements or {}
    result.metrics["fact_count"] = len(facts)
    result.metrics["facts_with_source_refs"] = sum(1 for fact in facts if fact.source_refs)
    result.checks["facts_present"] = bool(facts)

    if not facts:
        result.issues.append(
            FactValidationIssue(
                code="facts_missing",
                severity="high",
                message=f"No canonical facts were produced for document {doc_meta.doc_id}.",
            )
        )
        return result

    available_statement_types = {
        statement_type
        for statement_type in set(statements) | {fact.statement_type for fact in facts}
        if statement_type in _CRITICAL_FACTS
    }

    missing_critical = 0
    for statement_type in sorted(available_statement_types):
        expected = _CRITICAL_FACTS[statement_type]
        missing = [
            concept
            for concept in expected
            if not any(
                _canonical_concept(fact.concept) == _canonical_concept(concept)
                for fact in facts
                if fact.statement_type == statement_type
            )
        ]
        if missing:
            missing_critical += len(missing)
            result.issues.append(
                FactValidationIssue(
                    code="missing_critical_facts",
                    severity="high",
                    message=f"Missing critical facts for {statement_type}: {', '.join(missing)}.",
                    concepts=missing,
                    statement_type=statement_type,
                )
            )
    result.metrics["missing_critical_fact_count"] = missing_critical
    result.checks["missing_critical_facts"] = missing_critical == 0

    duplicates: dict[tuple[str, str, object, object], list[FinancialFact]] = defaultdict(list)
    for fact in facts:
        duplicates[(fact.statement_type, _canonical_concept(fact.concept), fact.period_start, fact.period_end)].append(fact)
    duplicate_groups = [group for group in duplicates.values() if len(group) > 1]
    result.metrics["duplicate_fact_groups"] = len(duplicate_groups)
    result.checks["duplicate_concepts"] = len(duplicate_groups) == 0
    for group in duplicate_groups:
        result.issues.append(
            FactValidationIssue(
                code="duplicate_concepts",
                severity="medium",
                message=(
                    f"Duplicate canonical facts detected for {group[0].statement_type}:{_canonical_concept(group[0].concept)}."
                ),
                fact_ids=[fact.fact_id for fact in group],
                concepts=[group[0].concept],
                statement_type=group[0].statement_type,
            )
        )

    expected_period_type = {"balance": "instant", "income": "duration", "cashflow": "duration"}
    period_issue_count = 0
    for statement_type in sorted(available_statement_types):
        facts_for_type = [fact for fact in facts if fact.statement_type == statement_type]
        non_null_period_ends = {fact.period_end for fact in facts_for_type if fact.period_end is not None}
        if len(non_null_period_ends) > 1:
            period_issue_count += 1
            result.issues.append(
                FactValidationIssue(
                    code="period_inconsistency",
                    severity="high",
                    message=f"Facts for {statement_type} use multiple period_end values.",
                    fact_ids=[fact.fact_id for fact in facts_for_type],
                    statement_type=statement_type,
                )
            )

        wrong_period_type = [
            fact
            for fact in facts_for_type
            if fact.period_type != "unknown" and fact.period_type != expected_period_type.get(statement_type)
        ]
        if wrong_period_type:
            period_issue_count += 1
            result.issues.append(
                FactValidationIssue(
                    code="period_type_inconsistency",
                    severity="high",
                    message=f"Facts for {statement_type} use an unexpected period_type.",
                    fact_ids=[fact.fact_id for fact in wrong_period_type],
                    statement_type=statement_type,
                )
            )
    result.metrics["period_issue_count"] = period_issue_count
    result.checks["period_consistency"] = period_issue_count == 0

    currency_scale_issue_count = 0
    for statement_type in sorted(available_statement_types):
        facts_for_type = [fact for fact in facts if fact.statement_type == statement_type]
        currencies = {fact.currency for fact in facts_for_type if fact.currency}
        scales = {fact.scale for fact in facts_for_type if fact.scale is not None}
        if len(currencies) > 1:
            currency_scale_issue_count += 1
            result.issues.append(
                FactValidationIssue(
                    code="currency_inconsistency",
                    severity="medium",
                    message=f"Facts for {statement_type} use multiple currencies: {', '.join(sorted(currencies))}.",
                    fact_ids=[fact.fact_id for fact in facts_for_type if fact.currency],
                    statement_type=statement_type,
                )
            )
        if len(scales) > 1:
            currency_scale_issue_count += 1
            result.issues.append(
                FactValidationIssue(
                    code="scale_inconsistency",
                    severity="medium",
                    message=f"Facts for {statement_type} use multiple scales.",
                    fact_ids=[fact.fact_id for fact in facts_for_type if fact.scale is not None],
                    statement_type=statement_type,
                )
            )
    result.metrics["currency_scale_issue_count"] = currency_scale_issue_count
    result.checks["scale_currency_consistency"] = currency_scale_issue_count == 0

    missing_ref_count = 0
    for statement_type, concepts in _CRITICAL_FACTS.items():
        for concept in concepts:
            _, matched = _fact_value(facts, statement_type, concept)
            if matched and not any(fact.source_refs for fact in matched):
                missing_ref_count += 1
                result.issues.append(
                    FactValidationIssue(
                        code="missing_source_refs",
                        severity="high",
                        message=f"Critical fact {statement_type}:{concept} is missing source references.",
                        fact_ids=[fact.fact_id for fact in matched],
                        concepts=[concept],
                        statement_type=statement_type,
                    )
                )
    result.metrics["critical_facts_missing_source_refs"] = missing_ref_count
    result.checks["critical_facts_have_source_refs"] = missing_ref_count == 0

    if "balance" in available_statement_types:
        total_assets, asset_facts = _fact_value(facts, "balance", "total_assets")
        total_liabilities, liability_facts = _fact_value(facts, "balance", "total_liabilities")
        total_equity, equity_facts = _fact_value(facts, "balance", "total_equity")
        if total_assets is None or total_liabilities is None or total_equity is None:
            result.checks["balance_equation"] = False
            result.issues.append(
                FactValidationIssue(
                    code="balance_equation_missing_facts",
                    severity="high",
                    message="Balance equation validation is missing one or more required facts.",
                    fact_ids=[fact.fact_id for fact in asset_facts + liability_facts + equity_facts],
                    statement_type="balance",
                )
            )
        else:
            diff_ratio = abs(total_assets - (total_liabilities + total_equity)) / max(abs(total_assets), 1.0)
            result.metrics["balance_equation_diff_ratio"] = diff_ratio
            result.checks["balance_equation"] = diff_ratio < tolerance
            if diff_ratio >= tolerance:
                result.issues.append(
                    FactValidationIssue(
                        code="balance_equation_failed",
                        severity="high",
                        message="Balance facts do not satisfy assets = liabilities + equity.",
                        fact_ids=[fact.fact_id for fact in asset_facts + liability_facts + equity_facts],
                        concepts=["total_assets", "total_liabilities", "total_equity"],
                        statement_type="balance",
                        metadata={"diff_ratio": diff_ratio},
                    )
                )

    if "cashflow" in available_statement_types:
        operating_cash_flow, operating_facts = _fact_value(facts, "cashflow", "operating_cash_flow")
        capex, capex_facts = _fact_value(facts, "cashflow", "capex")
        if operating_cash_flow is None or capex is None:
            result.checks["cashflow_reconciliation"] = False
            result.issues.append(
                FactValidationIssue(
                    code="cashflow_reconciliation_missing_facts",
                    severity="medium",
                    message="Cashflow reconciliation is missing operating cash flow or capex.",
                    fact_ids=[fact.fact_id for fact in operating_facts + capex_facts],
                    concepts=["operating_cash_flow", "capex"],
                    statement_type="cashflow",
                )
            )
        else:
            free_cash_flow = operating_cash_flow + capex
            result.metrics["free_cash_flow"] = free_cash_flow
            result.checks["cashflow_reconciliation"] = capex <= 0
            if capex > 0:
                result.issues.append(
                    FactValidationIssue(
                        code="cashflow_reconciliation_failed",
                        severity="medium",
                        message="Capex is positive; expected a cash outflow value for reconciliation.",
                        fact_ids=[fact.fact_id for fact in operating_facts + capex_facts],
                        concepts=["operating_cash_flow", "capex"],
                        statement_type="cashflow",
                        metadata={"free_cash_flow": free_cash_flow},
                    )
                )

    return result
