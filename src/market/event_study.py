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
    if "Close" in prices.columns:
        series = prices["Close"].pct_change().fillna(0)
    else:
        series = prices.iloc[:, 0].pct_change().fillna(0)

    cumulative_return = float(series.sum())
    volatility = float(series.std())

    return EventStudyResult(
        event_date=event_date,
        window=window,
        returns={"cumulative_return": cumulative_return},
        volatility={"std_dev": volatility},
        volume={},
        data_source="",
    )
