from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from src.agent.adapters.base import ExternalAgentClient
from src.schemas.models import AnalysisContext, DeepAnalysisResult


class HermesAgentClient(ExternalAgentClient):
    def __init__(self, base_url: str, *, api_key: str = "", timeout_s: int = 60) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    def analyze(
        self,
        context: AnalysisContext,
        *,
        task: str,
        options: dict[str, Any] | None = None,
    ) -> DeepAnalysisResult:
        payload = {
            "task": task,
            "context": context.model_dump(mode="json"),
            "options": options or {},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/analyze",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Hermes agent returned HTTP {exc.code}: {detail[:300]}") from exc

        data = json.loads(raw)
        if isinstance(data, dict) and "data" in data and data.get("ok") is not False:
            data = data["data"]
        return DeepAnalysisResult.model_validate(data)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers


def get_hermes_agent_client() -> HermesAgentClient | None:
    url = os.getenv("HERMES_AGENT_URL", "").strip()
    if not url:
        return None
    timeout_s = int(os.getenv("HERMES_AGENT_TIMEOUT_S", "60"))
    return HermesAgentClient(
        url,
        api_key=os.getenv("HERMES_AGENT_API_KEY", ""),
        timeout_s=timeout_s,
    )