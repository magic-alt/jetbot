from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    def get_prices(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        ...

    def get_volume(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        ...


class DummyMarketDataProvider:
    def get_prices(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_volume(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        return pd.DataFrame()


class YFinanceMarketDataProvider:
    def get_prices(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf

        return yf.download(ticker, start=start.isoformat(), end=end.isoformat())

    def get_volume(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        data = self.get_prices(ticker, start, end)
        if "Volume" in data.columns:
            return data[["Volume"]]
        return pd.DataFrame()
