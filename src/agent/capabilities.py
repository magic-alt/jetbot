from __future__ import annotations

import os

from src.llm.base import get_llm_model_config, is_llm_provider_configured
from src.schemas.models import AgentCapability


def get_agent_capabilities() -> list[AgentCapability]:
    deep_config = get_llm_model_config("deep_analysis")
    hermes_enabled = bool(os.getenv("HERMES_AGENT_URL", "").strip())
    deep_llm_enabled = is_llm_provider_configured(deep_config.provider)
    return [
        AgentCapability(
            capability_id="pdf_ingestion",
            name="PDF ingestion and OCR assist",
            description="Extract page text, images, and sparse-page OCR candidates from uploaded financial PDFs.",
            enabled=True,
            provider="local",
            inputs=["raw.pdf"],
            outputs=["pages", "needs_ocr"],
        ),
        AgentCapability(
            capability_id="financial_extraction",
            name="Financial statement extraction",
            description="Extract income statement, balance sheet, cashflow statement, notes, and source evidence.",
            enabled=True,
            provider="local+llm",
            inputs=["pages", "tables"],
            outputs=["statements", "notes", "validation_results"],
        ),
        AgentCapability(
            capability_id="risk_signals",
            name="Evidence-backed risk signals",
            description="Generate deterministic and model-assisted financial risk signals grounded in extracted data.",
            enabled=True,
            provider="local+llm",
            inputs=["statements", "notes", "validation_results"],
            outputs=["risk_signals"],
        ),
        AgentCapability(
            capability_id="deep_analysis",
            name="Deep financial analysis",
            description="Run second-pass analysis over a token-budgeted PDF evidence pack using Hermes or the configured LLM provider.",
            enabled=deep_llm_enabled or hermes_enabled,
            provider="hermes" if hermes_enabled else deep_config.provider,
            inputs=["analysis_context"],
            outputs=["deep_analysis", "agent_runs"],
        ),
        AgentCapability(
            capability_id="hermes_agent",
            name="Hermes external agent adapter",
            description="Reserved external-agent boundary for HTTP/JSON Hermes integration, replaceable by SDK or MCP later.",
            enabled=hermes_enabled,
            provider="hermes" if hermes_enabled else None,
            inputs=["analysis_context"],
            outputs=["deep_analysis"],
        ),
    ]