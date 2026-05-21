"""Tests for _parse_number and _detect_statement_type in src/agent/nodes.py."""
from __future__ import annotations


from src.agent.nodes import _parse_number, _detect_statement_type, _split_text, _statement_from_pages
from src.agent.state import AgentState
from src.schemas.models import DocumentMeta, Page, Table, TableCell


# ---------- _parse_number ----------

class TestParseNumber:
    def test_basic_integer(self):
        assert _parse_number("1234") == 1234.0

    def test_basic_float(self):
        assert _parse_number("12.34") == 12.34

    def test_thousands_separator(self):
        assert _parse_number("1,234,567.89") == 1234567.89

    def test_parenthetical_negative(self):
        assert _parse_number("(1234.56)") == -1234.56

    def test_fullwidth_parenthetical_negative(self):
        assert _parse_number("\uff081234.56\uff09") == -1234.56  # （1234.56）

    def test_triangle_negative(self):
        assert _parse_number("△1234") == -1234.0

    def test_dash_negative(self):
        assert _parse_number("-1234") == -1234.0

    def test_fullwidth_dash_negative(self):
        assert _parse_number("\uff0d1234") == -1234.0  # －1234

    def test_percent(self):
        result = _parse_number("15.5%")
        assert result is not None
        assert abs(result - 0.155) < 1e-9

    def test_fullwidth_percent(self):
        result = _parse_number("50\uff05")  # 50％
        assert result is not None
        assert abs(result - 0.50) < 1e-9

    def test_currency_rmb(self):
        assert _parse_number("\u00a51000") == 1000.0  # ¥1000

    def test_currency_dollar(self):
        assert _parse_number("$1000") == 1000.0

    def test_unit_wan(self):
        assert _parse_number("100\u4e07") == 100 * 1e4  # 100万

    def test_unit_wan_yuan(self):
        assert _parse_number("100\u4e07\u5143") == 100 * 1e4  # 100万元

    def test_unit_yi(self):
        assert _parse_number("5\u4ebf") == 5 * 1e8  # 5亿

    def test_unit_yi_yuan(self):
        assert _parse_number("5\u4ebf\u5143") == 5 * 1e8  # 5亿元

    def test_unit_baiwan(self):
        assert _parse_number("3\u767e\u4e07") == 3 * 1e6  # 3百万

    def test_space_separator(self):
        assert _parse_number("1 234 567") == 1234567.0

    def test_none_input(self):
        assert _parse_number(None) is None

    def test_empty_string(self):
        assert _parse_number("") is None

    def test_non_numeric(self):
        assert _parse_number("abc") is None


# ---------- _detect_statement_type ----------

class TestDetectStatementType:
    def _make_table(self, text: str) -> Table:
        return Table(
            table_id="t1",
            page=1,
            title=None,
            cells=[TableCell(row=0, col=0, text=text)],
            n_rows=1,
            n_cols=1,
            source_refs=[],
        )

    def test_balance_sheet_english(self):
        assert _detect_statement_type(self._make_table("Balance Sheet")) == "balance"

    def test_balance_sheet_chinese(self):
        assert _detect_statement_type(self._make_table("\u8d44\u4ea7\u8d1f\u503a\u8868")) == "balance"

    def test_income_statement(self):
        assert _detect_statement_type(self._make_table("Income Statement")) == "income"

    def test_profit_and_loss(self):
        assert _detect_statement_type(self._make_table("Profit and Loss")) == "income"

    def test_income_chinese(self):
        assert _detect_statement_type(self._make_table("\u5229\u6da6\u8868")) == "income"

    def test_cashflow_english(self):
        assert _detect_statement_type(self._make_table("Statement of Cash Flows")) == "cashflow"

    def test_cashflow_chinese(self):
        assert _detect_statement_type(self._make_table("\u73b0\u91d1\u6d41\u91cf\u8868")) == "cashflow"

    def test_unrecognized(self):
        assert _detect_statement_type(self._make_table("Notes to Financial Statements")) is None


# ---------- _statement_from_pages ----------

class TestStatementFromPages:
    def _make_state(self, pages: list[Page]) -> AgentState:
        return AgentState(doc_meta=DocumentMeta(doc_id="doc-1", filename="apple.pdf"), pages=pages)

    def test_extracts_apple_income_annual_values(self):
        state = self._make_state([
            Page(
                page_number=1,
                text=(
                    "Apple Inc. CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS "
                    "Total net sales (1) 94,930 89,498 391,035 383,285 "
                    "Total cost of sales 51,051 49,071 210,352 214,137 "
                    "Net income $ 14,736 $ 22,956 $ 93,736 $ 96,995"
                ),
            )
        ])

        statement = _statement_from_pages(state, "income")

        assert statement.totals["revenue"] == 391035.0
        assert statement.totals["cost_of_goods_sold"] == 210352.0
        assert statement.totals["net_income"] == 93736.0

    def test_extracts_apple_balance_and_cashflow_values(self):
        state = self._make_state([
            Page(page_number=2, text="Total assets $ 364,980 $ 352,583 Total liabilities 308,030 290,437 Total shareholders’ equity 56,950 62,146"),
            Page(page_number=3, text="Cash generated by operating activities 118,254 110,543 Cash used in financing activities (121,983) (108,488)"),
        ])

        balance = _statement_from_pages(state, "balance")
        cashflow = _statement_from_pages(state, "cashflow")

        assert balance.totals["total_assets"] == 364980.0
        assert balance.totals["total_liabilities"] == 308030.0
        assert balance.totals["total_equity"] == 56950.0
        assert cashflow.totals["operating_cf"] == 118254.0
        assert cashflow.totals["financing_cf"] == -121983.0


# ---------- _split_text ----------

class TestSplitText:
    def test_short_text_no_split(self):
        result = _split_text("hello world", target_size=100)
        assert result == ["hello world"]

    def test_paragraph_split(self):
        text = "A" * 50 + "\n\n" + "B" * 50
        result = _split_text(text, target_size=60)
        assert len(result) == 2

    def test_oversized_paragraph_gets_split(self):
        # Single paragraph longer than target_size
        text = "\u3002".join(["X" * 30] * 10)  # ~300 chars, sentences separated by 。
        result = _split_text(text, target_size=100)
        assert all(len(part) <= 100 for part in result)

    def test_hard_cut_on_no_sentence_boundary(self):
        text = "A" * 500  # no sentence boundaries
        result = _split_text(text, target_size=100)
        assert all(len(part) <= 100 for part in result)
        assert "".join(result) == text
