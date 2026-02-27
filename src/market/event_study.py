from __future__ import annotations

from datetime import date

import pandas as pd

from src.schemas.models import EventStudyResult


def run_event_study(prices: pd.DataFrame, event_date: date, window: tuple[int, int]) -> EventStudyResult:
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

    # Locate the event date within the index (find nearest trading day)
    event_ts = pd.Timestamp(event_date)
    if event_ts in prices.index:
        event_idx = prices.index.get_loc(event_ts)
    else:
        # Find the nearest index position at or after the event date
        candidates = prices.index[prices.index >= event_ts]
        if candidates.empty:
            candidates = prices.index
        event_idx = prices.index.get_loc(candidates[0])

    # Apply event window (window[0] is start offset, window[1] is end offset)
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

    if "Close" in windowed.columns:
        close_series = windowed["Close"]
    else:
        close_series = windowed.iloc[:, 0]

    daily_returns = close_series.pct_change().fillna(0)

    # Use geometric (compound) cumulative return: (1+r1)*(1+r2)*...*(1+rn) - 1
    cumulative_return = float((1 + daily_returns).prod() - 1)
    volatility = float(daily_returns.std())

    volume_stats: dict[str, float] = {}
    if "Volume" in windowed.columns:
        vol = windowed["Volume"]
        volume_stats["mean_volume"] = float(vol.mean())
        volume_stats["max_volume"] = float(vol.max())

    return EventStudyResult(
        event_date=event_date,
        window=window,
        returns={"cumulative_return": cumulative_return},
        volatility={"std_dev": volatility},
        volume=volume_stats,
        data_source="",
    )
