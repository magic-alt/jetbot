from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from src.api.routes import router
from src.utils.logging import configure_logging
from src.utils.metrics_collector import metrics
from src.utils.tracing import init_tracing

load_dotenv()
configure_logging()
init_tracing()

app = FastAPI(title="Financial Report Agent", version="0.1.0")

# ── CORS ──────────────────────────────────────────────────────────────────────
_cors_origins = os.getenv("CORS_ORIGINS", "*")
_allowed_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security headers ──────────────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add defensive HTTP headers to every response."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


# ── Rate limiter ──────────────────────────────────────────────────────────────
def _read_rate_limits() -> dict[str, int]:
    return {
        "upload": int(os.getenv("RATE_LIMIT_UPLOAD", "5")),
        "analyze": int(os.getenv("RATE_LIMIT_ANALYZE", "10")),
        "read": int(os.getenv("RATE_LIMIT_READ", "60")),
    }


def _classify_request(path: str, method: str) -> str:
    if method == "POST" and re.search(r"/documents$", path):
        return "upload"
    if method == "POST" and path.endswith("/analyze"):
        return "analyze"
    return "read"


class _RateLimiter:
    """Simple sliding-window per-IP rate limiter (no external dependencies)."""

    def __init__(self) -> None:
        self._windows: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        with self._lock:
            window = self._windows[key]
            while window and window[0] < now - 60.0:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True


_limiter = _RateLimiter()

_RATE_LIMIT_BODY = (
    '{"ok":false,"data":null,'
    '"error":{"code":"rate_limited","message":"Too many requests. Please slow down."}}'
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter middleware."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Health check and metrics are always exempt
        if request.url.path in ("/health", "/v1/health", "/metrics"):
            return await call_next(request)

        limits = _read_rate_limits()
        limit_type = _classify_request(request.url.path, request.method)
        limit = limits[limit_type]
        ip = (request.client.host if request.client else "unknown") or "unknown"
        key = f"{ip}:{limit_type}"

        if not _limiter.is_allowed(key, limit):
            return Response(
                content=_RATE_LIMIT_BODY,
                status_code=429,
                media_type="application/json",
            )
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)

app.include_router(router, prefix="/v1")


# ── Health endpoint (no auth, not rate-limited) ────────────────────────────
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


# ── Prometheus metrics endpoint (no auth, not rate-limited) ──────────────
@app.get("/metrics")
async def prometheus_metrics() -> Response:
    return Response(
        content=metrics.generate_metrics(),
        media_type=metrics.content_type,
    )
