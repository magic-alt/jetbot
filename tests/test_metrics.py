from __future__ import annotations

from src.schemas.models import (
    FinancialStatement,
    KeyNote,
    RiskSignal,
    SourceRef,
    StatementLineItem,
)
from src.utils.metrics import (
    balance_equation_pass_rate,
    compute_golden_metrics,
    note_type_recall,
    signal_category_recall,
    source_ref_completeness,
    statement_accuracy,
)


def _make_ref(page: int = 1) -> SourceRef:
    return SourceRef(ref_type="page_text", page=page, table_id=None, quote="test", confidence=0.5)


def _make_statement(
    kind: str,
    totals: dict[str, float],
    line_items: list[StatementLineItem] | None = None,
) -> FinancialStatement:
    return FinancialStatement(
        statement_type=kind,
        line_items=line_items or [],
        totals=totals,
        extraction_confidence=0.9,
        issues=[],
    )


# ---- statement_accuracy ----


class TestStatementAccuracy:
    def test_all_match(self) -> None:
        stmt = _make_statement("balance", {"total_assets": 100.0, "total_liabilities": 40.0, "total_equity": 60.0})
        result = statement_accuracy(stmt, {"total_assets": 100.0, "total_liabilities": 40.0, "total_equity": 60.0})
        assert result["accuracy"] == 1.0
        assert len(result["matched"]) == 3
        assert result["mismatched"] == []
        assert result["missing"] == []

    def test_partial_mismatch(self) -> None:
        stmt = _make_statement("balance", {"total_assets": 100.0, "total_liabilities": 40.0, "total_equity": 50.0})
        result = statement_accuracy(stmt, {"total_assets": 100.0, "total_equity": 60.0}, tolerance=0.05)
        assert "total_assets" in result["matched"]
        assert len(result["mismatched"]) == 1
        assert result["mismatched"][0]["key"] == "total_equity"
        assert result["accuracy"] == 0.5

    def test_missing_key(self) -> None:
        stmt = _make_statement("income", {"revenue": 500.0})
        result = statement_accuracy(stmt, {"revenue": 500.0, "net_income": 100.0})
        assert "revenue" in result["matched"]
        assert "net_income" in result["missing"]
        assert result["accuracy"] == 0.5

    def test_empty_expected(self) -> None:
        stmt = _make_statement("income", {"revenue": 500.0})
        result = statement_accuracy(stmt, {})
        assert result["accuracy"] == 1.0
        assert result["matched"] == []

    def test_fallback_to_line_items(self) -> None:
        items = [
            StatementLineItem(
                name_raw="Net Income", name_norm="net_income",
                value_current=100.0, value_prior=None, source_refs=[],
            )
        ]
        stmt = _make_statement("income", {"revenue": 500.0}, line_items=items)
        result = statement_accuracy(stmt, {"net_income": 100.0})
        assert result["accuracy"] == 1.0
        assert "net_income" in result["matched"]

    def test_tolerance_boundary(self) -> None:
        stmt = _make_statement("balance", {"total_assets": 105.0})
        # Exactly at 5% boundary
        result = statement_accuracy(stmt, {"total_assets": 100.0}, tolerance=0.05)
        assert "total_assets" in result["matched"]

        # Just over 5%
        stmt2 = _make_statement("balance", {"total_assets": 106.0})
        result2 = statement_accuracy(stmt2, {"total_assets": 100.0}, tolerance=0.05)
        assert len(result2["mismatched"]) == 1


# ---- balance_equation_pass_rate ----


class TestBalanceEquationPassRate:
    def test_all_pass(self) -> None:
        s1 = {"balance": _make_statement("balance", {"total_assets": 100, "total_liabilities": 40, "total_equity": 60})}
        s2 = {"balance": _make_statement("balance", {"total_assets": 200, "total_liabilities": 80, "total_equity": 120})}
        assert balance_equation_pass_rate([s1, s2]) == 1.0

    def test_one_fail(self) -> None:
        s1 = {"balance": _make_statement("balance", {"total_assets": 100, "total_liabilities": 40, "total_equity": 60})}
        s2 = {"balance": _make_statement("balance", {"total_assets": 100, "total_liabilities": 40, "total_equity": 30})}
        assert balance_equation_pass_rate([s1, s2]) == 0.5

    def test_no_balance(self) -> None:
        s1 = {"income": _make_statement("income", {"revenue": 100})}
        # No balance statements at all, should return 1.0
        assert balance_equation_pass_rate([s1]) == 1.0

    def test_missing_totals_counts_as_fail(self) -> None:
        s1 = {"balance": _make_statement("balance", {"total_assets": 100})}
        assert balance_equation_pass_rate([s1]) == 0.0

    def test_empty_list(self) -> None:
        assert balance_equation_pass_rate([]) == 1.0

    def test_mixed_with_and_without_balance(self) -> None:
        s_pass = {"balance": _make_statement("balance", {"total_assets": 100, "total_liabilities": 40, "total_equity": 60})}
        s_no_balance = {"income": _make_statement("income", {"revenue": 200})}
        s_fail = {"balance": _make_statement("balance", {"total_assets": 100, "total_liabilities": 40, "total_equity": 20})}
        # Only s_pass and s_fail have balance; s_pass passes, s_fail fails
        assert balance_equation_pass_rate([s_pass, s_no_balance, s_fail]) == 0.5


# ---- source_ref_completeness ----


class TestSourceRefCompleteness:
    def test_all_have_refs(self) -> None:
        notes = [
            KeyNote(note_type="other", summary="test", source_refs=[_make_ref()]),
            KeyNote(note_type="audit_opinion", summary="test2", source_refs=[_make_ref()]),
        ]
        signals = [
            RiskSignal(signal_id="s1", category="other", title="t", severity="low", description="d", evidence=[_make_ref()]),
        ]
        assert source_ref_completeness(notes, signals) == 1.0

    def test_partial_refs(self) -> None:
        notes = [
            KeyNote(note_type="other", summary="test", source_refs=[_make_ref()]),
            KeyNote(note_type="audit_opinion", summary="test2", source_refs=[]),
        ]
        signals = [
            RiskSignal(signal_id="s1", category="other", title="t", severity="low", description="d", evidence=[_make_ref()]),
            RiskSignal(signal_id="s2", category="accruals", title="t2", severity="medium", description="d2", evidence=[]),
        ]
        assert source_ref_completeness(notes, signals) == 0.5

    def test_empty_refs(self) -> None:
        notes = [KeyNote(note_type="other", summary="test", source_refs=[])]
        signals = [RiskSignal(signal_id="s1", category="other", title="t", severity="low", description="d", evidence=[])]
        assert source_ref_completeness(notes, signals) == 0.0

    def test_no_items(self) -> None:
        assert source_ref_completeness([], []) == 1.0

    def test_only_notes(self) -> None:
        notes = [KeyNote(note_type="other", summary="test", source_refs=[_make_ref()])]
        assert source_ref_completeness(notes, []) == 1.0

    def test_only_signals(self) -> None:
        signals = [RiskSignal(signal_id="s1", category="other", title="t", severity="low", description="d", evidence=[_make_ref()])]
        assert source_ref_completeness([], signals) == 1.0


# ---- signal_category_recall ----


class TestSignalCategoryRecall:
    def test_full_recall(self) -> None:
        assert signal_category_recall({"cash_vs_profit", "accruals", "other"}, {"cash_vs_profit", "accruals"}) == 1.0

    def test_partial_recall(self) -> None:
        assert signal_category_recall({"cash_vs_profit"}, {"cash_vs_profit", "accruals"}) == 0.5

    def test_no_recall(self) -> None:
        assert signal_category_recall({"other"}, {"cash_vs_profit", "accruals"}) == 0.0

    def test_empty_expected(self) -> None:
        assert signal_category_recall({"cash_vs_profit"}, set()) == 1.0

    def test_empty_actual(self) -> None:
        assert signal_category_recall(set(), {"cash_vs_profit"}) == 0.0

    def test_both_empty(self) -> None:
        assert signal_category_recall(set(), set()) == 1.0


# ---- note_type_recall ----


class TestNoteTypeRecall:
    def test_full_recall(self) -> None:
        assert note_type_recall({"audit_opinion", "related_party", "impairment"}, {"audit_opinion", "related_party"}) == 1.0

    def test_partial_recall(self) -> None:
        assert note_type_recall({"audit_opinion"}, {"audit_opinion", "related_party"}) == 0.5

    def test_no_recall(self) -> None:
        assert note_type_recall({"other"}, {"audit_opinion", "related_party"}) == 0.0

    def test_empty_expected(self) -> None:
        assert note_type_recall({"audit_opinion"}, set()) == 1.0

    def test_empty_actual(self) -> None:
        assert note_type_recall(set(), {"audit_opinion"}) == 0.0


# ---- compute_golden_metrics ----


class TestComputeGoldenMetrics:
    def test_empty_results(self) -> None:
        summary = compute_golden_metrics([])
        assert summary["n_cases"] == 0
        assert summary["avg_statement_accuracy"] == 0.0

    def test_single_perfect_result(self) -> None:
        stmt = _make_statement("balance", {"total_assets": 100, "total_liabilities": 40, "total_equity": 60})
        note = KeyNote(note_type="audit_opinion", summary="clean", source_refs=[_make_ref()])
        signal = RiskSignal(signal_id="s1", category="cash_vs_profit", title="t", severity="low", description="d", evidence=[_make_ref()])

        result = {
            "statements": {"balance": stmt},
            "notes": [note],
            "risk_signals": [signal],
            "expected_totals": {"balance": {"total_assets": 100, "total_liabilities": 40, "total_equity": 60}},
            "expected_note_types": {"audit_opinion"},
            "expected_signal_categories": {"cash_vs_profit"},
        }
        summary = compute_golden_metrics([result])
        assert summary["n_cases"] == 1
        assert summary["avg_statement_accuracy"] == 1.0
        assert summary["balance_equation_pass_rate"] == 1.0
        assert summary["avg_source_ref_completeness"] == 1.0
        assert summary["avg_signal_category_recall"] == 1.0
        assert summary["avg_note_type_recall"] == 1.0

    def test_multiple_results_averaged(self) -> None:
        stmt1 = _make_statement("income", {"revenue": 100.0, "net_income": 20.0})
        stmt2 = _make_statement("income", {"revenue": 200.0, "net_income": 50.0})

        r1 = {
            "statements": {"income": stmt1},
            "notes": [KeyNote(note_type="other", summary="t", source_refs=[_make_ref()])],
            "risk_signals": [],
            "expected_totals": {"income": {"revenue": 100.0, "net_income": 20.0}},
            "expected_note_types": {"other"},
            "expected_signal_categories": set(),
        }
        r2 = {
            "statements": {"income": stmt2},
            "notes": [KeyNote(note_type="other", summary="t", source_refs=[])],
            "risk_signals": [],
            "expected_totals": {"income": {"revenue": 200.0, "net_income": 50.0}},
            "expected_note_types": {"other"},
            "expected_signal_categories": set(),
        }
        summary = compute_golden_metrics([r1, r2])
        assert summary["n_cases"] == 2
        assert summary["avg_statement_accuracy"] == 1.0
        # r1 has 1/1 completeness, r2 has 0/1 completeness => avg = 0.5
        assert summary["avg_source_ref_completeness"] == 0.5
