"""Report generation, event study, and finalization pipeline nodes."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from src.agent.analysis_nodes import (
    _build_rag_context,
    _call_llm_structured,
    _load_prompt,
    _numbers_snapshot,
)
from src.agent.state import AgentState
from src.finance.facts import facts_from_statements
from src.llm.base import StructuredPromptRequest
from src.schemas.models import TraderReport
from src.storage.backend import get_storage_backend
from src.utils.document_metadata import enrich_document_meta
from src.utils.logging import get_logger, log_node
from src.utils.time import monotonic_ms


logger = get_logger(__name__)


class TraderReportDraft(BaseModel):
    executive_summary: str = ""
    key_drivers: list[str] = Field(default_factory=list)
    numbers_snapshot: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline node functions
# ---------------------------------------------------------------------------


def build_trader_report(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    system = _load_prompt("trader_report_prompt.md")
    context = _build_rag_context(
        state,
        query="executive summary key drivers financial snapshot risk limitations",
        top_k=10,
    )

    snapshot = _numbers_snapshot(state)
    request = StructuredPromptRequest(
        system_template=system,
        user_template=(
            "Document metadata JSON:\n{doc_meta}\n"
            "Validation JSON:\n{validation_results}\n"
            "Risk signals JSON:\n{risk_signals}\n"
            "Notes JSON:\n{notes}\n"
            "Deep analysis JSON:\n{deep_analysis}\n"
            "Retrieved context:\n{context}\n"
            "Current numbers snapshot JSON:\n{numbers_snapshot}\n"
            "Return a concise report object with fields: executive_summary, key_drivers, "
            "numbers_snapshot, limitations."
        ),
        input_values={
            "doc_meta": json.dumps(state.doc_meta.model_dump(mode="json"), ensure_ascii=False),
            "validation_results": json.dumps(state.validation_results, ensure_ascii=False),
            "risk_signals": json.dumps([s.model_dump(mode="json") for s in state.risk_signals], ensure_ascii=False),
            "notes": json.dumps([n.model_dump(mode="json") for n in state.notes], ensure_ascii=False),
            "deep_analysis": state.deep_analysis.model_dump_json() if state.deep_analysis else "{}",
            "context": context,
            "numbers_snapshot": json.dumps(snapshot, ensure_ascii=False),
        },
        output_model=TraderReportDraft,
    )

    draft = _call_llm_structured(
        state,
        request,
        node_name="build_trader_report",
        fallback=TraderReportDraft(
            executive_summary=f"Parsed {len(state.pages)} pages for {state.doc_meta.filename}.",
            key_drivers=["See extracted statements and notes."],
            numbers_snapshot=snapshot,
            limitations=["Not financial advice.", "Outputs depend on PDF extraction quality."],
        ),
    )

    report = TraderReport(
        doc_id=state.doc_meta.doc_id,
        executive_summary=draft.executive_summary or f"Parsed {len(state.pages)} pages for {state.doc_meta.filename}.",
        key_drivers=draft.key_drivers or ["See extracted statements and notes."],
        numbers_snapshot=draft.numbers_snapshot or snapshot,
        risk_signals=state.risk_signals,
        notes=state.notes,
        limitations=sorted(
            set(
                [
                    "Not financial advice.",
                    "Outputs depend on PDF extraction quality.",
                ]
                + draft.limitations
                + (state.deep_analysis.limitations if state.deep_analysis else [])
            )
        ),
    )

    state.trader_report = report
    state.debug["report_ready"] = True
    log_node(logger, state.doc_meta.doc_id, "build_trader_report", start_ms)
    return state


def run_event_study_node(state: AgentState) -> AgentState:
    """Optional node: runs event study if market data is available.

    Looks for a ticker in doc_meta.company or debug['ticker'].
    Uses DummyMarketDataProvider by default (no-op).
    When real market data is configured, performs multi-window event study
    and optionally saves a chart PNG.
    """
    start_ms = monotonic_ms()
    from src.market.event_study import run_multi_window_study, save_event_study_chart
    from src.market.provider import get_market_data_provider

    provider = get_market_data_provider()
    ticker = state.debug.get("ticker") or state.doc_meta.company or ""
    event_date = state.doc_meta.period_end

    if not ticker or not event_date:
        state.debug["event_study"] = "skipped:no_ticker_or_date"
        log_node(logger, state.doc_meta.doc_id, "run_event_study_node", start_ms)
        return state

    try:
        from datetime import timedelta
        # Fetch price data: 150 days before to 10 days after event
        start = event_date - timedelta(days=150)
        end = event_date + timedelta(days=10)
        prices = provider.get_prices(ticker, start, end)

        if prices.empty:
            state.debug["event_study"] = "skipped:no_price_data"
            log_node(logger, state.doc_meta.doc_id, "run_event_study_node", start_ms)
            return state

        results = run_multi_window_study(prices, event_date)
        state.event_study_results = results
        state.debug["event_study"] = f"completed:{len(results)}_windows"

        # Save chart
        data_dir = state.data_dir or "data"
        store = get_storage_backend(data_dir)
        report_dir = store.ensure_layout(state.doc_meta.doc_id).get("report")
        if report_dir:
            chart_path = Path(str(report_dir)) / "event_study.png"
            save_event_study_chart(prices, event_date, (-5, 5), chart_path)
            state.debug["event_study_chart"] = str(chart_path)

    except Exception as exc:
        state.errors.append(f"event_study_failed:{exc}")
        state.debug["event_study"] = f"failed:{exc}"

    log_node(logger, state.doc_meta.doc_id, "run_event_study_node", start_ms)
    return state


def finalize(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    # Remove non-serializable cached objects from debug before saving
    state.debug.pop("_rag_index", None)

    store = get_storage_backend(state.data_dir or "data")
    state.doc_meta = enrich_document_meta(state.doc_meta, state.pages)
    store.save_meta(state.doc_meta.doc_id, state.doc_meta)
    store.save_json(state.doc_meta.doc_id, "extracted/pages.json", [p.model_dump(mode="json") for p in state.pages])
    store.save_json(state.doc_meta.doc_id, "extracted/tables.json", [t.model_dump(mode="json") for t in state.tables])
    store.save_json(state.doc_meta.doc_id, "extracted/statements.json", {k: v.model_dump(mode="json") for k, v in state.statements.items()})
    if not state.facts:
        state.facts = facts_from_statements(state.doc_meta, state.statements)
    store.save_json(state.doc_meta.doc_id, "extracted/facts.json", [fact.model_dump(mode="json") for fact in state.facts])
    if state.fact_validation_results:
        store.save_json(
            state.doc_meta.doc_id,
            "extracted/fact_validation.json",
            state.fact_validation_results.model_dump(mode="json"),
        )
    if state.corrections:
        store.save_json(
            state.doc_meta.doc_id,
            "extracted/corrections.json",
            [correction.model_dump(mode="json") for correction in state.corrections],
        )
    if state.extraction_traces:
        store.save_json(
            state.doc_meta.doc_id,
            "extracted/extraction_traces.json",
            [trace.model_dump(mode="json") for trace in state.extraction_traces],
        )
    store.save_json(state.doc_meta.doc_id, "extracted/notes.json", [n.model_dump(mode="json") for n in state.notes])
    store.save_json(state.doc_meta.doc_id, "extracted/risk_signals.json", [s.model_dump(mode="json") for s in state.risk_signals])
    if state.analysis_context:
        store.save_json(
            state.doc_meta.doc_id,
            "extracted/analysis_context.json",
            state.analysis_context.model_dump(mode="json"),
        )
    if state.deep_analysis:
        store.save_json(
            state.doc_meta.doc_id,
            "extracted/deep_analysis.json",
            state.deep_analysis.model_dump(mode="json"),
        )
    if state.agent_runs:
        store.save_json(
            state.doc_meta.doc_id,
            "extracted/agent_runs.json",
            [run.model_dump(mode="json") for run in state.agent_runs],
        )
    if state.event_study_results:
        store.save_json(
            state.doc_meta.doc_id,
            "extracted/event_study.json",
            [r.model_dump(mode="json") for r in state.event_study_results],
        )
    if state.trader_report:
        store.save_json(
            state.doc_meta.doc_id,
            "report/trader_report.json",
            state.trader_report.model_dump(mode="json"),
        )
        store.save_markdown(state.doc_meta.doc_id, "report/trader_report.md", _render_markdown_report(state))
    log_node(logger, state.doc_meta.doc_id, "finalize", start_ms)
    return state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_markdown_report(state: AgentState) -> str:
    report = state.trader_report
    if not report:
        return ""
    lines = [
        f"# Trader Report for {state.doc_meta.filename}",
        "",
        "## Executive Summary",
        report.executive_summary,
        "",
        "## Key Drivers",
    ]
    for driver in report.key_drivers:
        lines.append(f"- {driver}")

    lines.extend(["", "## Numbers Snapshot"])
    for key, value in report.numbers_snapshot.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Risk Signals"])
    for signal in report.risk_signals:
        lines.append(f"- {signal.title} ({signal.severity}): {signal.description}")
        for ref in signal.evidence:
            lines.append(f"  - Evidence: page {ref.page} ({ref.ref_type}) {ref.quote or ''}")

    if state.deep_analysis:
        lines.extend(["", "## Deep Analysis", state.deep_analysis.summary])
        for finding in state.deep_analysis.findings:
            lines.append(f"- {finding.title} ({finding.severity}): {finding.summary}")
            for ref in finding.evidence:
                lines.append(f"  - Evidence: page {ref.page} ({ref.ref_type}) {ref.quote or ''}")

    lines.extend(["", "## Notes"])
    for note in report.notes:
        lines.append(f"- {note.note_type}: {note.summary}")
        for ref in note.source_refs:
            lines.append(f"  - Evidence: page {ref.page} ({ref.ref_type}) {ref.quote or ''}")

    lines.extend(["", "## Limitations"])
    for limitation in report.limitations:
        lines.append(f"- {limitation}")

    lines.append(f"\nGenerated at {report.created_at.isoformat()}.")
    return "\n".join(lines)
