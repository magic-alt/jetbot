"""Local market data cache with file-based persistence and TTL."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date
from pathlib import Path

import pandas as pd


class MarketDataCache:
    """File-based market data cache with configurable TTL.

    Cached data is stored as JSON files under ``{cache_dir}/{hash}.json``.
    Each entry tracks its creation timestamp so stale entries can be evicted.
    """

    def __init__(self, cache_dir: str | None = None, ttl_seconds: int | None = None) -> None:
        self._cache_dir = Path(cache_dir or os.getenv("DATA_DIR", "data")) / ".market_cache"
        self._ttl = ttl_seconds or int(os.getenv("MARKET_CACHE_TTL", "86400"))  # 24h default

    @staticmethod
    def _cache_key(ticker: str, start: date, end: date) -> str:
        raw = f"{ticker}:{start.isoformat()}:{end.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, ticker: str, start: date, end: date) -> pd.DataFrame | None:
        """Return cached DataFrame or None if not found / expired."""
        key = self._cache_key(ticker, start, end)
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        # Check TTL
        created_at = raw.get("created_at", 0)
        if time.time() - created_at > self._ttl:
            path.unlink(missing_ok=True)
            return None
        # Reconstruct DataFrame
        data = raw.get("data")
        if not data:
            return None
        df = pd.DataFrame(data)
        if "index" in df.columns:
            df = df.set_index("index")
            df.index = pd.to_datetime(df.index)
            df.index.name = None
        return df

    def put(self, ticker: str, start: date, end: date, df: pd.DataFrame) -> None:
        """Cache a DataFrame."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        key = self._cache_key(ticker, start, end)
        path = self._cache_dir / f"{key}.json"
        # Serialize DataFrame to list of dicts with index column
        records = df.reset_index().rename(columns={df.index.name or df.reset_index().columns[0]: "index"})
        data = records.to_dict(orient="records")
        for row in data:
            for k, v in row.items():
                if isinstance(v, pd.Timestamp):
                    row[k] = v.isoformat()
        payload = {
            "created_at": time.time(),
            "ticker": ticker,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "data": data,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def invalidate(self, ticker: str, start: date, end: date) -> None:
        """Remove a specific cache entry."""
        key = self._cache_key(ticker, start, end)
        path = self._cache_dir / f"{key}.json"
        path.unlink(missing_ok=True)

    def clear(self) -> int:
        """Remove all cache entries. Returns count of removed files."""
        if not self._cache_dir.exists():
            return 0
        count = 0
        for f in self._cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)
            count += 1
        return count
