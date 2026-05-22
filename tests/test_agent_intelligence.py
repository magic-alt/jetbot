from __future__ import annotations

from src.agent.capabilities import get_agent_capabilities
from src.agent.context import build_analysis_context
from src.agent.state import AgentState
from src.llm.base import get_llm_model_config
from src.schemas.models import (
    DocumentMeta,
    FinancialStatement,
    KeyNote,
    Page,
    RiskSignal,
    SourceRef,
    StatementLineItem,
)


def test_context_builder_preserves_metrics_and_evidence():
    source = SourceRef(ref_type="page_text", page=1, table_id=None, quote="Revenue 100", confidence=0.7)
    state = AgentState(
        doc_meta=DocumentMeta(doc_id="doc-1", filename="report.pdf", language="en"),
        pages=[Page(page_number=1, text="Revenue 100 Net income 20", images=[])],
        statements={
            "income": FinancialStatement(
                statement_type="income",
                totals={"revenue": 100.0, "net_income": 20.0},
                line_items=[
                    StatementLineItem(
                        name_raw="Revenue",
                        name_norm="revenue",
                        value_current=100.0,
                        source_refs=[source],
                    )
                ],
                extraction_confidence=0.8,
            )
        },
        notes=[KeyNote(note_type="other", summary="No unusual disclosures.", source_refs=[source])],
        risk_signals=[
            RiskSignal(
                signal_id="risk-1",
                category="other",
                title="Revenue quality",
                severity="low",
                description="Revenue and profit are both positive.",
                evidence=[source],
            )
        ],
        validation_results={"issues": [], "checks": {"balance_equation": 0.0}, "metrics": {}},
    )

    context = build_analysis_context(state, token_budget=1000)

    assert context.doc_id == "doc-1"
    assert context.statement_snapshot["income.revenue"] == 100.0
    assert context.sources
    assert any(ref.page == 1 for source_item in context.sources for ref in source_item.source_refs)
    assert context.tokens_estimate <= context.token_budget


def test_llm_model_config_supports_deepseek_and_ollama(monkeypatch):
    monkeypatch.setenv("LLM_DEEP_ANALYSIS_MODEL", "deepseek:deepseek-chat")
    deepseek = get_llm_model_config("deep_analysis")
    assert deepseek.provider == "deepseek"
    assert deepseek.model == "deepseek-chat"

    monkeypatch.setenv("LLM_DEEP_ANALYSIS_MODEL", "ollama:qwen2.5")
    ollama = get_llm_model_config("deep_analysis")
    assert ollama.provider == "ollama"
    assert ollama.model == "qwen2.5"


def test_capabilities_include_deep_analysis(monkeypatch):
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "mock:mock")
    capabilities = get_agent_capabilities()
    ids = {capability.capability_id for capability in capabilities}
    assert "deep_analysis" in ids
    assert "hermes_agent" in ids