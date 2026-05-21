from __future__ import annotations

from typing import Any, Protocol

from src.schemas.models import AnalysisContext, DeepAnalysisResult


class ExternalAgentClient(Protocol):
    def analyze(
        self,
        context: AnalysisContext,
        *,
        task: str,
        options: dict[str, Any] | None = None,
    ) -> DeepAnalysisResult:
        ...