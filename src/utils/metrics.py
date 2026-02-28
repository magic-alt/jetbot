"""Accuracy metrics for evaluation."""
from __future__ import annotations

from typing import Any

from src.schemas.models import FinancialStatement, KeyNote, RiskSignal, SourceRef


def statement_accuracy(
    actual: FinancialStatement,
    expected_totals: dict[str, float],
    tolerance: float = 0.05,
) -> dict[str, Any]:
    """Compare actual statement totals against expected values.

    Returns dict with 'matched', 'mismatched', 'missing', 'accuracy' keys.
    - matched: list of keys where actual is within tolerance of expected
    - mismatched: list of dicts with key, actual, expected, diff_ratio
    - missing: list of keys expected but not present in actual totals
    - accuracy: fraction of expected keys that matched
    """
    matched: list[str] = []
    mismatched: list[dict[str, Any]] = []
    missing: list[str] = []

    for key, expected_val in expected_totals.items():
        actual_val = actual.totals.get(key)
        if actual_val is None:
            # Also check line_items by name_norm
            for item in actual.line_items:
                if item.name_norm == key and item.value_current is not None:
                    actual_val = item.value_current
                    break

        if actual_val is None:
            missing.append(key)
            continue

        denominator = max(abs(expected_val), 1e-6)
        diff_ratio = abs(actual_val - expected_val) / denominator

        if diff_ratio <= tolerance:
            matched.append(key)
        else:
            mismatched.append({
                "key": key,
                "actual": actual_val,
                "expected": expected_val,
                "diff_ratio": diff_ratio,
            })

    total_expected = len(expected_totals)
    accuracy = len(matched) / total_expected if total_expected > 0 else 1.0

    return {
        "matched": matched,
        "mismatched": mismatched,
        "missing": missing,
        "accuracy": accuracy,
    }


def balance_equation_pass_rate(statements_list: list[dict[str, FinancialStatement]]) -> float:
    """Compute fraction of statement sets where balance equation holds.

    For each statement set, checks if total_assets == total_liabilities + total_equity
    within a 2% tolerance. Sets without a balance statement are excluded.
    """
    checked = 0
    passed = 0
    tolerance = 0.02

    for statements in statements_list:
        balance = statements.get("balance")
        if balance is None:
            continue

        total_assets = balance.totals.get("total_assets")
        total_liabilities = balance.totals.get("total_liabilities")
        total_equity = balance.totals.get("total_equity")

        if total_assets is None or total_liabilities is None or total_equity is None:
            # Check line items as fallback
            for item in balance.line_items:
                if item.name_norm == "total_assets" and item.value_current is not None:
                    total_assets = total_assets or item.value_current
                elif item.name_norm == "total_liabilities" and item.value_current is not None:
                    total_liabilities = total_liabilities or item.value_current
                elif item.name_norm == "total_equity" and item.value_current is not None:
                    total_equity = total_equity or item.value_current

        if total_assets is None or total_liabilities is None or total_equity is None:
            checked += 1
            # Missing totals counts as a failure
            continue

        checked += 1
        diff_ratio = abs(total_assets - (total_liabilities + total_equity)) / max(abs(total_assets), 1e-6)
        if diff_ratio <= tolerance:
            passed += 1

    return passed / checked if checked > 0 else 1.0


def source_ref_completeness(notes: list[KeyNote], signals: list[RiskSignal]) -> float:
    """Compute fraction of notes + signals that have at least one source_ref.

    Notes use the ``source_refs`` field; signals use the ``evidence`` field.
    """
    total = len(notes) + len(signals)
    if total == 0:
        return 1.0

    with_refs = 0
    for note in notes:
        if note.source_refs:
            with_refs += 1
    for signal in signals:
        if signal.evidence:
            with_refs += 1

    return with_refs / total


def signal_category_recall(
    actual_categories: set[str],
    expected_categories: set[str],
) -> float:
    """Compute recall of expected signal categories.

    Returns the fraction of expected categories that appear in actual.
    If expected is empty, returns 1.0.
    """
    if not expected_categories:
        return 1.0
    hits = actual_categories & expected_categories
    return len(hits) / len(expected_categories)


def note_type_recall(
    actual_types: set[str],
    expected_types: set[str],
) -> float:
    """Compute recall of expected note types.

    Returns the fraction of expected types that appear in actual.
    If expected is empty, returns 1.0.
    """
    if not expected_types:
        return 1.0
    hits = actual_types & expected_types
    return len(hits) / len(expected_types)


def compute_golden_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate metrics across multiple golden test results.

    Each result dict should contain:
      - 'statements': dict[str, FinancialStatement]
      - 'notes': list[KeyNote]
      - 'risk_signals': list[RiskSignal]
      - 'expected_totals': dict[str, dict[str, float]] (per statement type)
      - 'expected_note_types': set[str]
      - 'expected_signal_categories': set[str]

    Returns summary dict with aggregated metrics.
    """
    if not results:
        return {
            "n_cases": 0,
            "avg_statement_accuracy": 0.0,
            "balance_equation_pass_rate": 0.0,
            "avg_source_ref_completeness": 0.0,
            "avg_signal_category_recall": 0.0,
            "avg_note_type_recall": 0.0,
        }

    statement_accuracies: list[float] = []
    statements_list: list[dict[str, FinancialStatement]] = []
    src_completeness_values: list[float] = []
    signal_recalls: list[float] = []
    note_recalls: list[float] = []

    for r in results:
        statements = r.get("statements", {})
        notes = r.get("notes", [])
        risk_signals = r.get("risk_signals", [])
        expected_totals = r.get("expected_totals", {})
        expected_note_types = r.get("expected_note_types", set())
        expected_signal_categories = r.get("expected_signal_categories", set())

        # Statement accuracy per type
        for st_type, exp_totals in expected_totals.items():
            if st_type in statements and exp_totals:
                acc = statement_accuracy(statements[st_type], exp_totals)
                statement_accuracies.append(acc["accuracy"])

        statements_list.append(statements)

        src_completeness_values.append(source_ref_completeness(notes, risk_signals))

        actual_categories = {s.category for s in risk_signals}
        signal_recalls.append(signal_category_recall(actual_categories, expected_signal_categories))

        actual_types = {n.note_type for n in notes}
        note_recalls.append(note_type_recall(actual_types, expected_note_types))

    n = len(results)
    return {
        "n_cases": n,
        "avg_statement_accuracy": (
            sum(statement_accuracies) / len(statement_accuracies)
            if statement_accuracies
            else 0.0
        ),
        "balance_equation_pass_rate": balance_equation_pass_rate(statements_list),
        "avg_source_ref_completeness": (
            sum(src_completeness_values) / len(src_completeness_values)
            if src_completeness_values
            else 0.0
        ),
        "avg_signal_category_recall": (
            sum(signal_recalls) / len(signal_recalls) if signal_recalls else 0.0
        ),
        "avg_note_type_recall": (
            sum(note_recalls) / len(note_recalls) if note_recalls else 0.0
        ),
    }
