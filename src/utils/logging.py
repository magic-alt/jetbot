from __future__ import annotations

import logging
from typing import Any

from src.utils.time import monotonic_ms


class ContextLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = {"doc_id": "-", "node_name": "-", "elapsed_ms": 0}
        extra.update(self.extra)
        extra.update(kwargs.get("extra", {}))
        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s doc_id=%(doc_id)s node=%(node_name)s elapsed_ms=%(elapsed_ms)s %(message)s",
    )


def get_logger(name: str, **extra: Any) -> ContextLoggerAdapter:
    logger = logging.getLogger(name)
    return ContextLoggerAdapter(logger, extra)


def log_node(logger: ContextLoggerAdapter, doc_id: str, node_name: str, start_ms: int) -> None:
    elapsed = max(monotonic_ms() - start_ms, 0)
    logger.info(
        "node_complete",
        extra={"doc_id": doc_id, "node_name": node_name, "elapsed_ms": elapsed},
    )
