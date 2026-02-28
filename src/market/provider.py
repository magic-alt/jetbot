from __future__ import annotations

import os
import re
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


class TushareMarketDataProvider:
    """Tushare provider for Chinese A-share market data.

    Requires TUSHARE_TOKEN env var. Returns DataFrame with DatetimeIndex
    and columns: Open, High, Low, Close, Volume.
    """

    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.getenv("TUSHARE_TOKEN", "")

    def _get_api(self):
        try:
            import tushare as ts
        except ImportError:
            raise RuntimeError("tushare is not installed: pip install tushare")
        if not self._token:
            raise RuntimeError("TUSHARE_TOKEN env var is not set")
        return ts.pro_api(self._token)

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        """Normalize ticker to tushare ts_code format (e.g. 600519.SH)."""
        ticker = ticker.strip().upper()
        if re.match(r"^\d{6}\.(SH|SZ)$", ticker):
            return ticker
        # Bare 6-digit code: detect exchange from prefix
        digits = re.sub(r"\D", "", ticker)
        if len(digits) == 6:
            if digits.startswith(("6", "9")):
                return f"{digits}.SH"
            return f"{digits}.SZ"
        return ticker

    def get_prices(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        api = self._get_api()
        ts_code = self._normalize_ticker(ticker)
        df = api.daily(
            ts_code=ts_code,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date").sort_index()
        rename = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "vol": "Volume"}
        df = df.rename(columns=rename)
        return df[["Open", "High", "Low", "Close", "Volume"]]

    def get_volume(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        data = self.get_prices(ticker, start, end)
        if "Volume" in data.columns:
            return data[["Volume"]]
        return pd.DataFrame()


class PolygonMarketDataProvider:
    """Polygon.io provider for US market data.

    Requires POLYGON_API_KEY env var. Returns DataFrame with DatetimeIndex
    and columns: Open, High, Low, Close, Volume.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("POLYGON_API_KEY", "")

    def get_prices(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        try:
            from polygon import RESTClient
        except ImportError:
            raise RuntimeError("polygon-api-client is not installed: pip install polygon-api-client")
        if not self._api_key:
            raise RuntimeError("POLYGON_API_KEY env var is not set")

        client = RESTClient(self._api_key)
        aggs = client.get_aggs(
            ticker=ticker.upper(),
            multiplier=1,
            timespan="day",
            from_=start.isoformat(),
            to=end.isoformat(),
        )
        if not aggs:
            return pd.DataFrame()

        rows = []
        for bar in aggs:
            rows.append({
                "Date": pd.Timestamp(bar.timestamp, unit="ms"),
                "Open": bar.open,
                "High": bar.high,
                "Low": bar.low,
                "Close": bar.close,
                "Volume": bar.volume,
            })
        df = pd.DataFrame(rows).set_index("Date").sort_index()
        return df

    def get_volume(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        data = self.get_prices(ticker, start, end)
        if "Volume" in data.columns:
            return data[["Volume"]]
        return pd.DataFrame()


# ── A-share detection ─────────────────────────────────────────────────────────

_A_SHARE_PATTERN = re.compile(
    r"^(\d{6}\.(SH|SZ|sh|sz))|"  # 600519.SH or 000001.SZ
    r"^(SH|SZ|sh|sz)\d{6}$|"     # SH600519
    r"^\d{6}$"                     # bare 6-digit code
)


def is_a_share_ticker(ticker: str) -> bool:
    """Return True if ticker looks like a Chinese A-share stock code."""
    return bool(_A_SHARE_PATTERN.match(ticker.strip()))


def get_market_data_provider(provider_name: str | None = None) -> MarketDataProvider:
    """Factory: returns appropriate provider based on config.

    Resolution order:
    1. Explicit provider_name argument
    2. MARKET_DATA_PROVIDER env var
    3. Default to DummyMarketDataProvider
    """
    name = (provider_name or os.getenv("MARKET_DATA_PROVIDER", "dummy")).lower()
    if name == "tushare":
        return TushareMarketDataProvider()
    if name == "polygon":
        return PolygonMarketDataProvider()
    if name == "yfinance":
        return YFinanceMarketDataProvider()
    return DummyMarketDataProvider()
