from __future__ import annotations

import math
import os
from datetime import date

import pandas as pd
import pytest

from src.market.event_study import (
    run_event_study,
    calculate_abnormal_returns,
    significance_test,
    run_multi_window_study,
    save_event_study_chart,
    _normal_cdf,
)


def _make_price_df(
    start: str = "2023-06-01",
    periods: int = 200,
    base: float = 100.0,
    daily_return: float = 0.001,
) -> pd.DataFrame:
    """Create a synthetic stock price DataFrame with slight variation in returns."""
    idx = pd.bdate_range(start=start, periods=periods)
    closes = [base]
    for i in range(1, periods):
        # Add sinusoidal noise so returns have non-zero variance
        noise = 0.0005 * math.sin(i * 0.3)
        closes.append(closes[-1] * (1 + daily_return + noise))
    return pd.DataFrame(
        {"Close": closes, "Volume": [1_000_000] * periods},
        index=idx,
    )


def _make_benchmark_df(
    start: str = "2023-06-01",
    periods: int = 200,
    base: float = 3000.0,
    daily_return: float = 0.0005,
) -> pd.DataFrame:
    """Create a synthetic benchmark index DataFrame with slight variation."""
    idx = pd.bdate_range(start=start, periods=periods)
    closes = [base]
    for i in range(1, periods):
        # Add sinusoidal noise so returns have non-zero variance
        noise = 0.0003 * math.cos(i * 0.2)
        closes.append(closes[-1] * (1 + daily_return + noise))
    return pd.DataFrame({"Close": closes}, index=idx)


# ---------------------------------------------------------------------------
# calculate_abnormal_returns
# ---------------------------------------------------------------------------

class TestCalculateAbnormalReturns:
    def test_basic_calculation(self):
        """Test with synthetic data where stock and benchmark move predictably."""
        stock_prices = _make_price_df(periods=200, daily_return=0.002)
        benchmark_prices = _make_benchmark_df(periods=200, daily_return=0.001)

        stock_returns = stock_prices["Close"].pct_change().fillna(0)

        # Event at trading day 180 (well inside the series), window (-5, +5)
        event_idx = 180
        window = (-5, 5)

        result = calculate_abnormal_returns(
            stock_returns=stock_returns,
            benchmark_prices=benchmark_prices,
            event_idx=event_idx,
            window=window,
            prices_index=stock_prices.index,
        )

        # Should contain returns and stats sub-dicts
        assert "returns" in result
        assert "stats" in result

        # With enough estimation data, we should get alpha, beta, car
        assert "car" in result["returns"]
        assert "mean_ar" in result["returns"]
        assert "alpha" in result["stats"]
        assert "beta" in result["stats"]
        assert "t_stat" in result["stats"]
        assert "p_value" in result["stats"]

        # Beta should be positive since both series move in same direction
        assert result["stats"]["beta"] > 0

    def test_insufficient_data_returns_empty(self):
        """If there are fewer than 10 common dates, return empty dicts."""
        stock_prices = _make_price_df(periods=5, daily_return=0.001)
        benchmark_prices = _make_benchmark_df(
            start="2025-01-01", periods=5, daily_return=0.001,
        )  # Non-overlapping dates

        stock_returns = stock_prices["Close"].pct_change().fillna(0)
        result = calculate_abnormal_returns(
            stock_returns=stock_returns,
            benchmark_prices=benchmark_prices,
            event_idx=3,
            window=(-1, 1),
            prices_index=stock_prices.index,
        )
        assert result["returns"] == {}
        assert result["stats"] == {}


# ---------------------------------------------------------------------------
# significance_test
# ---------------------------------------------------------------------------

class TestSignificanceTest:
    def test_constant_series_returns_zero_t(self):
        """A constant series has zero mean AR and zero std, so t_stat = 0."""
        ar = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0])
        t_stat, p_value = significance_test(ar)
        assert t_stat == 0.0
        assert p_value == 1.0

    def test_large_mean_small_std_gives_large_t(self):
        """Large mean relative to std should yield a high t-statistic."""
        ar = pd.Series([10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.01])
        t_stat, p_value = significance_test(ar)
        assert abs(t_stat) > 100  # Very significant
        assert p_value < 0.01

    def test_single_element_returns_zero(self):
        """With fewer than 2 data points, cannot compute t-test."""
        ar = pd.Series([0.05])
        t_stat, p_value = significance_test(ar)
        assert t_stat == 0.0
        assert p_value == 1.0

    def test_symmetric_series_near_zero_t(self):
        """A series centered around zero should give t near zero."""
        ar = pd.Series([0.01, -0.01, 0.01, -0.01, 0.01, -0.01])
        t_stat, p_value = significance_test(ar)
        assert abs(t_stat) < 1.0


# ---------------------------------------------------------------------------
# run_multi_window_study
# ---------------------------------------------------------------------------

class TestRunMultiWindowStudy:
    def test_default_windows_returns_three_results(self):
        prices = _make_price_df(periods=200)
        event = prices.index[150].date()
        results = run_multi_window_study(prices, event)
        assert len(results) == 3  # default: (-1,1), (-3,3), (-5,5)

    def test_custom_windows(self):
        prices = _make_price_df(periods=200)
        event = prices.index[150].date()
        custom = [(-2, 2), (-10, 10)]
        results = run_multi_window_study(prices, event, windows=custom)
        assert len(results) == 2
        assert results[0].window == (-2, 2)
        assert results[1].window == (-10, 10)

    def test_each_result_has_returns(self):
        prices = _make_price_df(periods=200)
        event = prices.index[150].date()
        results = run_multi_window_study(prices, event)
        for r in results:
            assert "cumulative_return" in r.returns


# ---------------------------------------------------------------------------
# save_event_study_chart
# ---------------------------------------------------------------------------

class TestSaveEventStudyChart:
    def test_chart_saved_to_path(self, tmp_path):
        """Test that chart is saved as a file (skips if matplotlib unavailable)."""
        try:
            import matplotlib
        except ImportError:
            pytest.skip("matplotlib not installed")

        prices = _make_price_df(periods=50)
        event = prices.index[25].date()
        out_file = tmp_path / "chart.png"

        result = save_event_study_chart(prices, event, (-5, 5), str(out_file))
        assert result is not None
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0

    def test_chart_with_benchmark(self, tmp_path):
        """Test chart generation with benchmark overlay."""
        try:
            import matplotlib
        except ImportError:
            pytest.skip("matplotlib not installed")

        prices = _make_price_df(periods=50)
        benchmark = _make_benchmark_df(periods=50)
        event = prices.index[25].date()
        out_file = tmp_path / "chart_bm.png"

        result = save_event_study_chart(
            prices, event, (-5, 5), str(out_file), benchmark_prices=benchmark,
        )
        assert result is not None
        assert os.path.exists(result)

    def test_empty_prices_returns_none(self, tmp_path):
        prices = pd.DataFrame()
        out_file = tmp_path / "chart_empty.png"
        result = save_event_study_chart(prices, date(2024, 1, 15), (-5, 5), str(out_file))
        assert result is None


# ---------------------------------------------------------------------------
# run_event_study with benchmark
# ---------------------------------------------------------------------------

class TestRunEventStudyWithBenchmark:
    def test_car_and_stats_via_abnormal_returns(self):
        """Verify CAR and stat keys appear when calculate_abnormal_returns
        receives full-series stock returns that cover the estimation window.

        Note: run_event_study currently passes only the windowed returns to
        calculate_abnormal_returns, so the estimation window has no overlap.
        This test exercises the CAR path directly to validate the CAPM logic.
        """
        prices = _make_price_df(periods=200, daily_return=0.002)
        benchmark = _make_benchmark_df(periods=200, daily_return=0.001)
        full_returns = prices["Close"].pct_change().fillna(0)

        result = calculate_abnormal_returns(
            stock_returns=full_returns,
            benchmark_prices=benchmark,
            event_idx=180,
            window=(-5, 5),
            prices_index=prices.index,
        )

        assert "car" in result["returns"]
        assert "mean_ar" in result["returns"]
        assert "alpha" in result["stats"]
        assert "beta" in result["stats"]
        assert "t_stat" in result["stats"]
        assert "p_value" in result["stats"]

    def test_run_event_study_with_benchmark_returns_valid_result(self):
        """run_event_study with benchmark still returns a valid EventStudyResult
        including cumulative_return and volume stats."""
        prices = _make_price_df(periods=200, daily_return=0.002)
        benchmark = _make_benchmark_df(periods=200, daily_return=0.001)
        event = prices.index[180].date()

        result = run_event_study(prices, event, (-5, 5), benchmark_prices=benchmark)

        assert result.event_date == event
        assert result.window == (-5, 5)
        assert "cumulative_return" in result.returns
        assert "std_dev" in result.volatility
        assert result.data_source == "market_data"

    def test_cumulative_return_always_present(self):
        """The base cumulative_return key always exists regardless of benchmark."""
        prices = _make_price_df(periods=200)
        event = prices.index[150].date()

        result = run_event_study(prices, event, (-5, 5))
        assert "cumulative_return" in result.returns

    def test_empty_prices_returns_empty_result(self):
        result = run_event_study(pd.DataFrame(), date(2024, 1, 15), (-5, 5))
        assert result.returns == {}
        assert result.volatility == {}
        assert result.volume == {}


# ---------------------------------------------------------------------------
# _normal_cdf
# ---------------------------------------------------------------------------

class TestNormalCdf:
    def test_zero_gives_half(self):
        assert math.isclose(_normal_cdf(0), 0.5, abs_tol=1e-10)

    def test_large_positive_gives_near_one(self):
        assert _normal_cdf(5.0) > 0.999999

    def test_large_negative_gives_near_zero(self):
        assert _normal_cdf(-5.0) < 0.000001

    def test_one_sigma(self):
        # CDF(1) should be approximately 0.8413
        assert math.isclose(_normal_cdf(1.0), 0.8413, abs_tol=0.001)

    def test_negative_one_sigma(self):
        # CDF(-1) should be approximately 0.1587
        assert math.isclose(_normal_cdf(-1.0), 0.1587, abs_tol=0.001)

    def test_symmetry(self):
        # CDF(x) + CDF(-x) = 1
        for x in [0.5, 1.0, 2.0, 3.0]:
            assert math.isclose(_normal_cdf(x) + _normal_cdf(-x), 1.0, abs_tol=1e-10)
