from __future__ import annotations

from typing import Any

from src.finance.utils import fallback_evidence, find_line_item, find_total
from src.schemas.models import FinancialStatement, KeyNote, RiskSignal, SourceRef
from src.utils.ids import new_doc_id


AUDIT_KEYWORDS = ["保留意见", "无法表示意见", "否定意见", "强调事项"]


def generate_signals(
    statements: dict[str, FinancialStatement],
    notes: list[KeyNote],
    validation_results: dict[str, Any],
    pages_text: list[str],
) -> list[RiskSignal]:
    signals: list[RiskSignal] = []

    evidence_fallback = fallback_evidence(pages_text)

    income_stmt = statements.get("income")
    cashflow_stmt = statements.get("cashflow")
    net_income = find_total(income_stmt, ["net_income"]) if income_stmt else None
    operating_cf = find_total(cashflow_stmt, ["operating_cf"]) if cashflow_stmt else None

    if net_income is not None and operating_cf is not None:
        if net_income > 0 and operating_cf < 0:
            severity = "high" if abs(operating_cf) > abs(net_income) else "medium"
            signals.append(
                RiskSignal(
                    signal_id=new_doc_id(),
                    category="cash_vs_profit",
                    title="Positive profit with negative operating cashflow",
                    severity=severity,
                    description="Net income is positive while operating cashflow is negative.",
                    metrics={"net_income": net_income, "operating_cf": operating_cf},
                    evidence=_pick_evidence(statements.get("cashflow"), evidence_fallback),
                )
            )

    working_capital_signal = _working_capital_signal(statements, evidence_fallback)
    if working_capital_signal:
        signals.append(working_capital_signal)

    if _has_disclosure_issue(validation_results):
        signals.append(
            RiskSignal(
                signal_id=new_doc_id(),
                category="disclosure_inconsistency",
                title="Statement reconciliation issues",
                severity="high",
                description="Balance equation or unit consistency checks failed.",
                metrics={"issues": ",".join(validation_results.get("issues", []))},
                evidence=evidence_fallback,
            )
        )

    audit_signal = _audit_governance_signal(notes, pages_text, evidence_fallback)
    if audit_signal:
        signals.append(audit_signal)

    return signals


def _pick_evidence(statement: FinancialStatement | None, fallback: list[SourceRef]) -> list[SourceRef]:
    if statement:
        for item in statement.line_items:
            if item.source_refs:
                return item.source_refs
    return fallback


def _working_capital_signal(
    statements: dict[str, FinancialStatement],
    fallback: list[SourceRef],
) -> RiskSignal | None:
    balance = statements.get("balance")
    income = statements.get("income")
    if not balance or not income:
        return None

    ar = find_line_item(balance, ["应收", "accounts receivable"])
    inventory = find_line_item(balance, ["存货", "inventory"])
    revenue = find_line_item(income, ["营业收入", "revenue"])

    if not ar or not revenue:
        return None
    if ar.value_current is None or ar.value_prior is None:
        return None
    if revenue.value_current is None or revenue.value_prior is None:
        return None

    ar_growth = (ar.value_current - ar.value_prior) / max(abs(ar.value_prior), 1.0)
    rev_growth = (revenue.value_current - revenue.value_prior) / max(abs(revenue.value_prior), 1.0)
    metrics = {"ar_growth": ar_growth, "rev_growth": rev_growth}
    if inventory and inventory.value_current is not None and inventory.value_prior is not None:
        inv_growth = (inventory.value_current - inventory.value_prior) / max(abs(inventory.value_prior), 1.0)
        metrics["inventory_growth"] = inv_growth

    if ar_growth - rev_growth > 0.2:
        return RiskSignal(
            signal_id=new_doc_id(),
            category="working_capital",
            title="Receivables growth outpaces revenue",
            severity="medium",
            description="Accounts receivable growth exceeds revenue growth.",
            metrics=metrics,
            evidence=_pick_evidence(balance, fallback),
        )
    return None


def _has_disclosure_issue(validation_results: dict[str, Any]) -> bool:
    issues = validation_results.get("issues", [])
    return any(
        issue in {"balance_equation_failed", "balance_missing_totals"} or issue.startswith("unit_mismatch")
        for issue in issues
    )


def _audit_governance_signal(
    notes: list[KeyNote],
    pages_text: list[str],
    fallback: list[SourceRef],
) -> RiskSignal | None:
    combined = "\n".join(note.summary for note in notes)
    combined += "\n".join(pages_text[:2])
    for keyword in AUDIT_KEYWORDS:
        if keyword in combined:
            return RiskSignal(
                signal_id=new_doc_id(),
                category="audit_governance",
                title="Audit opinion flags",
                severity="medium" if keyword == "强调事项" else "high",
                description=f"Audit opinion contains keyword: {keyword}.",
                metrics={"keyword": keyword},
                evidence=fallback,
            )
    return None
