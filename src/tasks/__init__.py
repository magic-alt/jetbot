"""Celery application and task queue configuration.

Usage:
    TASK_BACKEND=celery  → dispatches to Celery worker via Redis broker
    TASK_BACKEND=background (default) → uses FastAPI BackgroundTasks

Start the worker::

    celery -A src.tasks worker --loglevel=info --concurrency=2
"""

from __future__ import annotations

import os

# Celery is an optional dependency; import guards allow the module to be
# loaded even when celery is not installed (e.g. in tests or when using
# the default ``background`` task backend).
try:
    from celery import Celery  # type: ignore[import-untyped]

    CELERY_AVAILABLE = True
except Exception:  # pragma: no cover
    Celery = None  # type: ignore[assignment]
    CELERY_AVAILABLE = False

_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", _BROKER_URL)

app: Celery | None = None

if CELERY_AVAILABLE and Celery is not None:
    app = Celery(
        "jetbot",
        broker=_BROKER_URL,
        backend=_RESULT_BACKEND,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )


def is_celery_backend() -> bool:
    """Return True when the operator has opted into the Celery task backend."""
    return os.getenv("TASK_BACKEND", "background").lower() == "celery" and CELERY_AVAILABLE
