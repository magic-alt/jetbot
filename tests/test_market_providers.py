from __future__ import annotations

import time
from datetime import date

import pandas as pd

from src.market.provider import (
    DummyMarketDataProvider,
    TushareMarketDataProvider,
    PolygonMarketDataProvider,
    YFinanceMarketDataProvider,
    is_a_share_ticker,
    get_market_data_provider,
)
from src.market.cache import MarketDataCache


# ---------------------------------------------------------------------------
# DummyMarketDataProvider
# ---------------------------------------------------------------------------

class TestDummyMarketDataProvider:
    def test_get_prices_returns_empty_dataframe(self):
        provider = DummyMarketDataProvider()
        df = provider.get_prices("AAPL", date(2024, 1, 1), date(2024, 6, 1))
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_get_volume_returns_empty_dataframe(self):
        provider = DummyMarketDataProvider()
        df = provider.get_volume("600519.SH", date(2024, 1, 1), date(2024, 6, 1))
        assert isinstance(df, pd.DataFrame)
        assert df.empty


# ---------------------------------------------------------------------------
# TushareMarketDataProvider._normalize_ticker
# ---------------------------------------------------------------------------

class TestTushareNormalizeTicker:
    def test_already_sh_suffix(self):
        assert TushareMarketDataProvider._normalize_ticker("600519.SH") == "600519.SH"

    def test_already_sz_suffix(self):
        assert TushareMarketDataProvider._normalize_ticker("000001.SZ") == "000001.SZ"

    def test_lowercase_suffix_normalized(self):
        assert TushareMarketDataProvider._normalize_ticker("600519.sh") == "600519.SH"

    def test_bare_6_digit_starts_with_6(self):
        # Codes starting with 6 go to SH
        assert TushareMarketDataProvider._normalize_ticker("600519") == "600519.SH"

    def test_bare_6_digit_starts_with_9(self):
        # Codes starting with 9 go to SH
        assert TushareMarketDataProvider._normalize_ticker("900001") == "900001.SH"

    def test_bare_6_digit_starts_with_0(self):
        # Codes starting with 0 go to SZ
        assert TushareMarketDataProvider._normalize_ticker("000001") == "000001.SZ"

    def test_bare_6_digit_starts_with_3(self):
        # Codes starting with 3 (ChiNext) go to SZ
        assert TushareMarketDataProvider._normalize_ticker("300750") == "300750.SZ"

    def test_sh_prefix_format(self):
        # SH600519 -> strips non-digits, starts with 6 -> SH
        assert TushareMarketDataProvider._normalize_ticker("SH600519") == "600519.SH"

    def test_sz_prefix_format(self):
        # SZ000001 -> strips non-digits, starts with 0 -> SZ
        assert TushareMarketDataProvider._normalize_ticker("SZ000001") == "000001.SZ"

    def test_whitespace_trimmed(self):
        assert TushareMarketDataProvider._normalize_ticker("  600519.SH  ") == "600519.SH"

    def test_non_standard_ticker_passthrough(self):
        # Non-6-digit code returns as-is (uppercased)
        assert TushareMarketDataProvider._normalize_ticker("AAPL") == "AAPL"


# ---------------------------------------------------------------------------
# PolygonMarketDataProvider
# ---------------------------------------------------------------------------

class TestPolygonMarketDataProvider:
    def test_constructor_accepts_api_key(self):
        provider = PolygonMarketDataProvider(api_key="test-key-123")
        assert provider._api_key == "test-key-123"

    def test_constructor_defaults_to_empty_without_env(self, monkeypatch):
        monkeypatch.delenv("POLYGON_API_KEY", raising=False)
        provider = PolygonMarketDataProvider()
        assert provider._api_key == ""


# ---------------------------------------------------------------------------
# is_a_share_ticker
# ---------------------------------------------------------------------------

class TestIsAShareTicker:
    def test_sh_suffix(self):
        assert is_a_share_ticker("600519.SH") is True

    def test_sz_suffix(self):
        assert is_a_share_ticker("000001.SZ") is True

    def test_lowercase_suffix(self):
        assert is_a_share_ticker("600519.sh") is True

    def test_sh_prefix(self):
        assert is_a_share_ticker("SH600519") is True

    def test_sz_prefix(self):
        assert is_a_share_ticker("SZ000001") is True

    def test_bare_6_digits(self):
        assert is_a_share_ticker("600519") is True

    def test_bare_6_digits_sz(self):
        assert is_a_share_ticker("000001") is True

    def test_us_ticker_not_a_share(self):
        assert is_a_share_ticker("AAPL") is False

    def test_hk_ticker_not_a_share(self):
        assert is_a_share_ticker("0700.HK") is False

    def test_short_number_not_a_share(self):
        assert is_a_share_ticker("12345") is False

    def test_whitespace_trimmed(self):
        assert is_a_share_ticker("  600519  ") is True


# ---------------------------------------------------------------------------
# get_market_data_provider factory
# ---------------------------------------------------------------------------

class TestGetMarketDataProvider:
    def test_default_returns_dummy(self, monkeypatch):
        monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
        provider = get_market_data_provider()
        assert isinstance(provider, DummyMarketDataProvider)

    def test_explicit_dummy(self):
        provider = get_market_data_provider("dummy")
        assert isinstance(provider, DummyMarketDataProvider)

    def test_tushare(self):
        provider = get_market_data_provider("tushare")
        assert isinstance(provider, TushareMarketDataProvider)

    def test_polygon(self):
        provider = get_market_data_provider("polygon")
        assert isinstance(provider, PolygonMarketDataProvider)

    def test_yfinance(self):
        provider = get_market_data_provider("yfinance")
        assert isinstance(provider, YFinanceMarketDataProvider)

    def test_case_insensitive(self):
        provider = get_market_data_provider("Tushare")
        assert isinstance(provider, TushareMarketDataProvider)

    def test_unknown_falls_back_to_dummy(self):
        provider = get_market_data_provider("nonexistent")
        assert isinstance(provider, DummyMarketDataProvider)


# ---------------------------------------------------------------------------
# MarketDataCache
# ---------------------------------------------------------------------------

class TestMarketDataCache:
    def test_put_and_get_roundtrip(self, tmp_path):
        cache = MarketDataCache(cache_dir=str(tmp_path), ttl_seconds=3600)
        idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        df = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=idx)
        cache.put("AAPL", date(2024, 1, 2), date(2024, 1, 4), df)
        result = cache.get("AAPL", date(2024, 1, 2), date(2024, 1, 4))
        assert result is not None
        assert len(result) == 3
        assert list(result.columns) == ["Close"]

    def test_ttl_expiration(self, tmp_path):
        cache = MarketDataCache(cache_dir=str(tmp_path), ttl_seconds=1)
        idx = pd.to_datetime(["2024-01-02"])
        df = pd.DataFrame({"Close": [100.0]}, index=idx)
        cache.put("AAPL", date(2024, 1, 2), date(2024, 1, 2), df)

        # Entry should exist immediately
        assert cache.get("AAPL", date(2024, 1, 2), date(2024, 1, 2)) is not None

        # Wait for TTL to expire
        time.sleep(1.1)
        assert cache.get("AAPL", date(2024, 1, 2), date(2024, 1, 2)) is None

    def test_invalidate_removes_entry(self, tmp_path):
        cache = MarketDataCache(cache_dir=str(tmp_path), ttl_seconds=3600)
        idx = pd.to_datetime(["2024-01-02"])
        df = pd.DataFrame({"Close": [100.0]}, index=idx)
        cache.put("AAPL", date(2024, 1, 2), date(2024, 1, 2), df)
        assert cache.get("AAPL", date(2024, 1, 2), date(2024, 1, 2)) is not None

        cache.invalidate("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        assert cache.get("AAPL", date(2024, 1, 2), date(2024, 1, 2)) is None

    def test_clear_removes_all_entries(self, tmp_path):
        cache = MarketDataCache(cache_dir=str(tmp_path), ttl_seconds=3600)
        idx = pd.to_datetime(["2024-01-02"])
        df = pd.DataFrame({"Close": [100.0]}, index=idx)
        cache.put("AAPL", date(2024, 1, 2), date(2024, 1, 2), df)
        cache.put("MSFT", date(2024, 1, 2), date(2024, 1, 2), df)

        count = cache.clear()
        assert count == 2
        assert cache.get("AAPL", date(2024, 1, 2), date(2024, 1, 2)) is None
        assert cache.get("MSFT", date(2024, 1, 2), date(2024, 1, 2)) is None

    def test_missing_entry_returns_none(self, tmp_path):
        cache = MarketDataCache(cache_dir=str(tmp_path), ttl_seconds=3600)
        result = cache.get("AAPL", date(2024, 1, 2), date(2024, 1, 4))
        assert result is None
