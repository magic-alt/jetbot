from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agent.nodes import (
    build_trader_report,
    detect_sections_and_chunk,
    extract_financial_statements,
    extract_key_notes,
    extract_tables,
    finalize,
    generate_risk_signals,
    ingest_pdf,
    validate_and_reconcile,
)
from src.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("ingest_pdf", _wrap(ingest_pdf))
    graph.add_node("extract_tables", _wrap(extract_tables))
    graph.add_node("detect_sections_and_chunk", _wrap(detect_sections_and_chunk))
    graph.add_node("extract_financial_statements", _wrap(extract_financial_statements))
    graph.add_node("validate_and_reconcile", _wrap(validate_and_reconcile))
    graph.add_node("extract_key_notes", _wrap(extract_key_notes))
    graph.add_node("generate_risk_signals", _wrap(generate_risk_signals))
    graph.add_node("build_trader_report", _wrap(build_trader_report))
    graph.add_node("finalize", _wrap(finalize))

    graph.set_entry_point("ingest_pdf")
    graph.add_edge("ingest_pdf", "extract_tables")
    graph.add_edge("extract_tables", "detect_sections_and_chunk")
    graph.add_edge("detect_sections_and_chunk", "extract_financial_statements")
    graph.add_edge("extract_financial_statements", "validate_and_reconcile")

    graph.add_conditional_edges(
        "validate_and_reconcile",
        _should_retry,
        {"retry": "extract_financial_statements", "ok": "extract_key_notes"},
    )

    graph.add_edge("extract_key_notes", "generate_risk_signals")
    graph.add_edge("generate_risk_signals", "build_trader_report")
    graph.add_edge("build_trader_report", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def _should_retry(state: dict) -> str:
    state_obj = AgentState.model_validate(state)
    if "validation_failed" in state_obj.errors and state_obj.retry_count < 2:
        return "retry"
    return "ok"


def _wrap(fn):
    def _inner(state: dict) -> dict:
        state_obj = AgentState.model_validate(state)
        next_state = fn(state_obj)
        return next_state.model_dump()

    return _inner
