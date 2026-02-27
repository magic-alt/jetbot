from __future__ import annotations

from typing import Any

from src.finance.utils import find_line_item, find_total
from src.schemas.models import FinancialStatement


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
