"""Event study analysis with CAPM abnormal returns, t-test, and chart generation."""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pandas as pd

from src.schemas.models import EventStudyResult


def run_event_study(
    prices: pd.DataFrame,
    event_date: date,
    window: tuple[int, int],
    *,
    benchmark_prices: pd.DataFrame | None = None,
) -> EventStudyResult:
    """Run event study with optional market-adjusted abnormal returns.

    Args:
        prices: Stock price DataFrame (must have 'Close' column, DatetimeIndex).
        event_date: The event date.
        window: (pre_days, post_days) event window, e.g. (-5, +5).
        benchmark_prices: Optional benchmark index prices for CAPM adjustment.

    Returns:
        EventStudyResult with returns, volatility, volume, and abnormal return stats.
    """
    if prices.empty:
        return EventStudyResult(
            event_date=event_date,
            window=window,
            returns={},
            volatility={},
            volume={},
            data_source="",
        )

    prices = prices.sort_index()

    # Locate event date in index
    event_ts = pd.Timestamp(event_date)
    if event_ts in prices.index:
        event_idx = prices.index.get_loc(event_ts)
    else:
        candidates = prices.index[prices.index >= event_ts]
        if candidates.empty:
            candidates = prices.index
        event_idx = prices.index.get_loc(candidates[0])

    start_idx = max(event_idx + window[0], 0)
    end_idx = min(event_idx + window[1] + 1, len(prices))
    windowed = prices.iloc[start_idx:end_idx]

    if windowed.empty:
        return EventStudyResult(
            event_date=event_date,
            window=window,
            returns={},
            volatility={},
            volume={},
            data_source="",
        )

    close = windowed["Close"] if "Close" in windowed.columns else windowed.iloc[:, 0]
    daily_returns = close.pct_change().fillna(0)
    cumulative_return = float((1 + daily_returns).prod() - 1)
    volatility_val = float(daily_returns.std())

    returns_dict: dict[str, float] = {"cumulative_return": cumulative_return}
    volatility_dict: dict[str, float] = {"std_dev": volatility_val}

    # ── CAPM abnormal returns ─────────────────────────────────────────────────
    if benchmark_prices is not None and not benchmark_prices.empty:
        ar_result = calculate_abnormal_returns(
            stock_returns=daily_returns,
            benchmark_prices=benchmark_prices,
            event_idx=event_idx,
            window=window,
            prices_index=prices.index,
        )
        returns_dict.update(ar_result.get("returns", {}))
        volatility_dict.update(ar_result.get("stats", {}))

    # ── Volume stats ──────────────────────────────────────────────────────────
    volume_stats: dict[str, float] = {}
    if "Volume" in windowed.columns:
        vol = windowed["Volume"]
        volume_stats["mean_volume"] = float(vol.mean())
        volume_stats["max_volume"] = float(vol.max())

    return EventStudyResult(
        event_date=event_date,
        window=window,
        returns=returns_dict,
        volatility=volatility_dict,
        volume=volume_stats,
        data_source="market_data",
    )


def calculate_abnormal_returns(
    stock_returns: pd.Series,
    benchmark_prices: pd.DataFrame,
    event_idx: int,
    window: tuple[int, int],
    prices_index: pd.DatetimeIndex,
) -> dict:
    """Calculate market-adjusted abnormal returns using simple market model.

    Uses an estimation window of 120 trading days before the event window
    to estimate alpha and beta via OLS regression: R_stock = alpha + beta * R_market.

    Returns dict with 'returns' and 'stats' sub-dicts.
    """
    result: dict = {"returns": {}, "stats": {}}

    benchmark = benchmark_prices.sort_index()
    bm_close = benchmark["Close"] if "Close" in benchmark.columns else benchmark.iloc[:, 0]
    bm_returns = bm_close.pct_change().fillna(0)

    # Align stock and benchmark by overlapping dates
    common_idx = stock_returns.index.intersection(bm_returns.index)
    if len(common_idx) < 10:
        return result

    stock_aligned = stock_returns.reindex(common_idx).fillna(0)
    bm_aligned = bm_returns.reindex(common_idx).fillna(0)

    # Estimation window: 120 days before event window start
    est_end = max(event_idx + window[0] - 1, 0)
    est_start = max(est_end - 120, 0)

    if est_end <= est_start or est_end >= len(prices_index):
        return result

    est_dates = prices_index[est_start:est_end]
    est_common = est_dates.intersection(common_idx)
    if len(est_common) < 20:
        return result

    est_stock = stock_aligned.reindex(est_common).fillna(0)
    est_bm = bm_aligned.reindex(est_common).fillna(0)

    # OLS: R_stock = alpha + beta * R_market
    bm_mean = float(est_bm.mean())
    stock_mean = float(est_stock.mean())
    cov = float(((est_stock - stock_mean) * (est_bm - bm_mean)).mean())
    var_bm = float(((est_bm - bm_mean) ** 2).mean())
    if var_bm < 1e-12:
        return result

    beta = cov / var_bm
    alpha = stock_mean - beta * bm_mean

    # Calculate abnormal returns in event window
    ev_start = max(event_idx + window[0], 0)
    ev_end = min(event_idx + window[1] + 1, len(prices_index))
    ev_dates = prices_index[ev_start:ev_end]
    ev_common = ev_dates.intersection(common_idx)

    if len(ev_common) == 0:
        return result

    ev_stock = stock_aligned.reindex(ev_common).fillna(0)
    ev_bm = bm_aligned.reindex(ev_common).fillna(0)

    expected_returns = alpha + beta * ev_bm
    abnormal_returns = ev_stock - expected_returns
    car = float(abnormal_returns.sum())  # Cumulative Abnormal Return

    # t-test for significance
    t_stat, p_value = significance_test(abnormal_returns)

    result["returns"]["car"] = car
    result["returns"]["mean_ar"] = float(abnormal_returns.mean())
    result["stats"]["alpha"] = alpha
    result["stats"]["beta"] = beta
    result["stats"]["t_stat"] = t_stat
    result["stats"]["p_value"] = p_value

    return result


def significance_test(abnormal_returns: pd.Series) -> tuple[float, float]:
    """Run t-test on abnormal returns.

    H0: mean abnormal return = 0.

    Returns (t_statistic, p_value). Uses two-tailed test.
    """
    n = len(abnormal_returns)
    if n < 2:
        return 0.0, 1.0

    mean_ar = float(abnormal_returns.mean())
    std_ar = float(abnormal_returns.std(ddof=1))
    if std_ar < 1e-12:
        return 0.0, 1.0

    t_stat = mean_ar / (std_ar / math.sqrt(n))

    # Approximate p-value using the normal distribution for simplicity
    # (accurate enough for n > 20; for smaller n this is conservative)
    p_value = 2.0 * _normal_cdf(-abs(t_stat))
    return t_stat, p_value


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF using Abramowitz & Stegun formula."""
    return 0.5 * math.erfc(-x / math.sqrt(2))


def run_multi_window_study(
    prices: pd.DataFrame,
    event_date: date,
    windows: list[tuple[int, int]] | None = None,
    *,
    benchmark_prices: pd.DataFrame | None = None,
) -> list[EventStudyResult]:
    """Run event study across multiple windows.

    Default windows: [(-1,+1), (-3,+3), (-5,+5)].
    """
    if windows is None:
        windows = [(-1, 1), (-3, 3), (-5, 5)]
    return [
        run_event_study(prices, event_date, w, benchmark_prices=benchmark_prices)
        for w in windows
    ]


def save_event_study_chart(
    prices: pd.DataFrame,
    event_date: date,
    window: tuple[int, int],
    out_path: str | Path,
    *,
    benchmark_prices: pd.DataFrame | None = None,
) -> str | None:
    """Save event study chart as PNG. Returns path on success, None on failure.

    The chart shows:
    - Stock price over the event window
    - Event date marker
    - Cumulative return annotation
    - Optional benchmark overlay
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        return None

    if prices.empty:
        return None

    prices = prices.sort_index()
    event_ts = pd.Timestamp(event_date)
    if event_ts in prices.index:
        event_idx = prices.index.get_loc(event_ts)
    else:
        candidates = prices.index[prices.index >= event_ts]
        if candidates.empty:
            return None
        event_idx = prices.index.get_loc(candidates[0])

    start_idx = max(event_idx + window[0], 0)
    end_idx = min(event_idx + window[1] + 1, len(prices))
    windowed = prices.iloc[start_idx:end_idx]

    if windowed.empty:
        return None

    close = windowed["Close"] if "Close" in windowed.columns else windowed.iloc[:, 0]

    fig, ax = plt.subplots(figsize=(10, 5))

    # Plot stock price
    ax.plot(close.index, close.values, "b-o", markersize=4, label="Stock Price")

    # Plot benchmark if available
    if benchmark_prices is not None and not benchmark_prices.empty:
        bm = benchmark_prices.sort_index()
        bm_close = bm["Close"] if "Close" in bm.columns else bm.iloc[:, 0]
        bm_windowed = bm_close.reindex(close.index, method="nearest")
        if not bm_windowed.empty:
            # Normalize both to 100 at start
            stock_norm = close / close.iloc[0] * 100
            bm_norm = bm_windowed / bm_windowed.iloc[0] * 100
            ax.clear()
            ax.plot(stock_norm.index, stock_norm.values, "b-o", markersize=4, label="Stock (indexed)")
            ax.plot(bm_norm.index, bm_norm.values, "g--s", markersize=3, label="Benchmark (indexed)")

    # Event date marker
    actual_event = prices.index[event_idx] if event_idx < len(prices) else event_ts
    ax.axvline(x=actual_event, color="r", linestyle="--", alpha=0.7, label=f"Event: {event_date}")

    # Cumulative return annotation
    daily_ret = close.pct_change().fillna(0)
    cum_ret = float((1 + daily_ret).prod() - 1)
    ax.set_title(f"Event Study [{window[0]}, +{window[1]}]  Cum. Return: {cum_ret:.2%}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Price / Index")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(out)
