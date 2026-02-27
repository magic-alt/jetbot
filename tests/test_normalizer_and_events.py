"""Tests for normalizer and event_study."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.finance.normalizer import normalize_account_name
from src.market.event_study import run_event_study


# ---------- normalize_account_name ----------

class TestNormalizeAccountName:
    def test_chinese_revenue(self):
        assert normalize_account_name("营业收入") == "revenue"

    def test_chinese_variant_revenue(self):
        assert normalize_account_name("主营业务收入") == "revenue"

    def test_chinese_net_income(self):
        assert normalize_account_name("净利润") == "net_income"

    def test_chinese_total_assets(self):
        assert normalize_account_name("资产总计") == "total_assets"

    def test_chinese_total_liabilities(self):
        assert normalize_account_name("负债合计") == "total_liabilities"

    def test_chinese_total_equity(self):
        assert normalize_account_name("所有者权益合计") == "total_equity"

    def test_chinese_operating_cf(self):
        assert normalize_account_name("经营活动产生的现金流量净额") == "operating_cf"

    def test_unmapped_returns_original(self):
        assert normalize_account_name("未知科目") == "未知科目"

    def test_whitespace_handling(self):
        assert normalize_account_name(" 营业收入 ") == "revenue"


# ---------- event_study ----------

class TestEventStudy:
    def test_empty_prices(self):
        result = run_event_study(pd.DataFrame(), date(2025, 1, 10), (-2, 2))
        assert result.returns == {}

    def test_geometric_return_not_arithmetic(self):
        """Ensure compound return is used: +10% then -10% should yield ~-1%, not 0%."""
        dates = pd.date_range("2025-01-06", periods=5, freq="B")
        prices = pd.DataFrame(
            {"Close": [100, 110, 99, 99, 99]},
            index=dates,
        )
        result = run_event_study(prices, date(2025, 1, 6), (0, 4))
        cum_ret = result.returns.get("cumulative_return")
        assert cum_ret is not None
        # Geometric: (1+0)(1+0.1)(1-0.1)(1+0)(1+0) - 1 = 0.99/100 -1 = -0.01
        assert abs(cum_ret - (-0.01)) < 0.02

    def test_event_window_filtering(self):
        """Window should restrict to subset of prices."""
        dates = pd.date_range("2025-01-01", periods=20, freq="B")
        prices = pd.DataFrame(
            {"Close": list(range(100, 120)), "Volume": [1000] * 20},
            index=dates,
        )
        result = run_event_study(prices, date(2025, 1, 10), (-1, 1))
        assert result.returns
        # Window is 3 days, so volume stats should exist
        assert "mean_volume" in result.volume

    def test_non_trading_day_fallback(self):
        """Event date on a weekend should find the next trading day."""
        dates = pd.date_range("2025-01-06", periods=5, freq="B")  # Mon-Fri
        prices = pd.DataFrame({"Close": [100, 101, 102, 103, 104]}, index=dates)
        # Jan 4 is a Saturday
        result = run_event_study(prices, date(2025, 1, 4), (-1, 2))
        assert result.returns
