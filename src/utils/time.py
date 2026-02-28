from __future__ import annotations

import time
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)
