from __future__ import annotations

from typing import Any

from src.schemas.models import FinancialStatement, StatementLineItem


def _find_total(statement: FinancialStatement, keys: list[str]) -> float | None:
    for key in keys:
        if key in statement.totals:
            return statement.totals[key]
    for item in statement.line_items:
        if item.name_norm in keys and item.value_current is not None:
            return item.value_current
    return None


def _unit_consistency(statement: FinancialStatement) -> list[str]:
    units = {item.unit for item in statement.line_items if item.unit}
    if len(units) > 1:
        return [f"unit_mismatch:{','.join(sorted(units))}"]
    return []


def _check_line_item_totals(statement: FinancialStatement) -> list[str]:
    totals = [item for item in statement.line_items if "total" in item.name_norm or "??" in item.name_raw or "??" in item.name_raw]
    if not totals:
        return []
    issues: list[str] = []
    for total in totals:
        if total.value_current is None:
            continue
        subtotal = sum(item.value_current or 0.0 for item in statement.line_items if item is not total)
        if abs(total.value_current - subtotal) / max(abs(total.value_current), 1.0) > 0.05:
            issues.append(f"line_total_mismatch:{total.name_raw}")
    return issues


def validate_statements(statements: dict[str, FinancialStatement], tolerance: float = 0.02) -> dict[str, Any]:
    results: dict[str, Any] = {"issues": [], "checks": {}, "metrics": {}}

    balance = statements.get("balance")
    if balance:
        total_assets = _find_total(balance, ["total_assets"])
        total_liabilities = _find_total(balance, ["total_liabilities"])
        total_equity = _find_total(balance, ["total_equity"])
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
        missing = [key for key in required if _find_total(income, [key]) is None]
        if missing:
            results["issues"].append(f"income_missing:{','.join(missing)}")
        results["issues"].extend(_unit_consistency(income))
        results["issues"].extend(_check_line_item_totals(income))

    cashflow = statements.get("cashflow")
    if cashflow:
        results["issues"].extend(_unit_consistency(cashflow))
        results["issues"].extend(_check_line_item_totals(cashflow))

    net_income = _find_total(income, ["net_income"]) if income else None
    operating_cf = _find_total(cashflow, ["operating_cf"]) if cashflow else None
    if net_income is not None and operating_cf is not None:
        results["metrics"]["profit_to_cfo_ratio"] = operating_cf / max(net_income, 1e-6)

    if balance and income:
        ar_item = _find_line_item(balance, ["应收", "accounts receivable"])
        rev_item = _find_line_item(income, ["营业收入", "revenue"])
        if ar_item and rev_item and ar_item.value_current is not None and ar_item.value_prior is not None:
            if rev_item.value_current is not None and rev_item.value_prior is not None:
                ar_growth = (ar_item.value_current - ar_item.value_prior) / max(abs(ar_item.value_prior), 1.0)
                rev_growth = (rev_item.value_current - rev_item.value_prior) / max(abs(rev_item.value_prior), 1.0)
                results["metrics"]["ar_growth_vs_rev_growth"] = ar_growth - rev_growth
    return results


def _find_line_item(statement: FinancialStatement, keywords: list[str]) -> StatementLineItem | None:
    for item in statement.line_items:
        name = f"{item.name_raw} {item.name_norm}".lower()
        for keyword in keywords:
            if keyword.lower() in name:
                return item
    return None
