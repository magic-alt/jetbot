from __future__ import annotations

import concurrent.futures
import os
import threading

from langgraph.graph import END, StateGraph

from src.agent.nodes import (
    build_analysis_context_node,
    build_trader_report,
    detect_sections_and_chunk,
    extract_financial_statements,
    extract_key_notes,
    extract_tables,
    finalize,
    generate_risk_signals,
    ingest_pdf,
    run_deep_analysis,
    run_event_study_node,
    validate_and_reconcile,
)
from src.agent.state import AgentState


# Cache AgentState instances by doc_id to avoid repeated full
# model_validate/model_dump round-trips on every node transition.
_state_cache: dict[str, AgentState] = {}
_state_cache_lock = threading.Lock()

# Shared executor for per-node timeout enforcement.
# Using a shared pool avoids the overhead of creating/destroying an executor
# on every node transition.
_timeout_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="node-timeout"
)

# Cached node timeout value (0 means no limit).
_NODE_TIMEOUT_S = int(os.getenv("NODE_TIMEOUT_S", "120"))


def get_cached_state(doc_id: str) -> AgentState | None:
    """Return the most recently cached AgentState for *doc_id*, or None."""
    with _state_cache_lock:
        return _state_cache.get(doc_id)


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("ingest_pdf", _wrap(ingest_pdf))
    graph.add_node("extract_tables", _wrap(extract_tables))
    graph.add_node("detect_sections_and_chunk", _wrap(detect_sections_and_chunk))
    graph.add_node("extract_financial_statements", _wrap(extract_financial_statements))
    graph.add_node("validate_and_reconcile", _wrap(validate_and_reconcile))
    graph.add_node("extract_key_notes", _wrap(extract_key_notes))
    graph.add_node("generate_risk_signals", _wrap(generate_risk_signals))
    graph.add_node("build_analysis_context", _wrap(build_analysis_context_node))
    graph.add_node("run_deep_analysis", _wrap(run_deep_analysis))
    graph.add_node("build_trader_report", _wrap(build_trader_report))
    graph.add_node("run_event_study_node", _wrap(run_event_study_node))
    graph.add_node("finalize", _wrap(finalize, cleanup_cache=True))

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
    graph.add_edge("generate_risk_signals", "build_analysis_context")
    graph.add_edge("build_analysis_context", "run_deep_analysis")
    graph.add_edge("run_deep_analysis", "build_trader_report")
    graph.add_edge("build_trader_report", "run_event_study_node")
    graph.add_edge("run_event_study_node", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def _should_retry(state: dict | AgentState) -> str:
    # Handle both dict and AgentState instances
    if isinstance(state, dict):
        errors = state.get("errors", [])
        retry_count = state.get("retry_count", 0)
    else:
        errors = state.errors
        retry_count = state.retry_count
    if "validation_failed" in errors and retry_count < 2:
        return "retry"
    return "ok"


def _wrap(fn, *, cleanup_cache: bool = False):
    def _inner(state) -> dict:
        # Handle both dict and AgentState instances from LangGraph
        if isinstance(state, AgentState):
            state_obj = state
            doc_id = state_obj.doc_meta.doc_id
        else:
            doc_meta = state.get("doc_meta", {})
            doc_id = doc_meta.get("doc_id", "") if isinstance(doc_meta, dict) else ""

            # Reuse cached AgentState to skip expensive model_validate
            if doc_id:
                with _state_cache_lock:
                    cached = _state_cache.get(doc_id)
                if cached is not None:
                    state_obj = cached
                else:
                    state_obj = AgentState.model_validate(state)
            else:
                state_obj = AgentState.model_validate(state)

        # Per-node timeout (0 means no limit)
        if _NODE_TIMEOUT_S > 0:
            future = _timeout_executor.submit(fn, state_obj)
            try:
                next_state = future.result(timeout=_NODE_TIMEOUT_S)
            except concurrent.futures.TimeoutError:
                state_obj.errors.append(
                    f"{fn.__name__}_timeout:{_NODE_TIMEOUT_S}s"
                )
                next_state = state_obj
        else:
            next_state = fn(state_obj)

        if doc_id:
            with _state_cache_lock:
                if cleanup_cache:
                    _state_cache.pop(doc_id, None)
                else:
                    _state_cache[doc_id] = next_state

        return next_state.model_dump()

    return _inner
