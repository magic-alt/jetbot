"""Analysis pipeline nodes — notes, signals, deep analysis, and shared helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.agent.adapters.hermes import get_hermes_agent_client
from src.agent.context import build_analysis_context as build_analysis_context_payload
from src.agent.state import AgentState
from src.finance.signals import generate_signals
from src.llm.base import StructuredPromptRequest, get_default_llm_client, get_llm_client, get_llm_model_config, langsmith_metadata
from src.schemas.models import (
    AgentRun,
    DeepAnalysisResult,
    FinancialStatement,
    KeyNote,
    ModelInvocation,
    RiskSignal,
    SourceRef,
    StatementLineItem,
)
from src.storage.vector_index import build_rag_index
from src.utils.ids import new_doc_id
from src.utils.logging import get_logger, log_node
from src.utils.time import monotonic_ms
from src.utils.time import utc_now


logger = get_logger(__name__)


class KeyNotesBundle(BaseModel):
    notes: list[KeyNote] = Field(default_factory=list)


class RiskSignalsBundle(BaseModel):
    risk_signals: list[RiskSignal] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline node functions
# ---------------------------------------------------------------------------


def extract_key_notes(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    system = _load_prompt("key_notes_prompt.md")
    context = _build_rag_context(
        state,
        query=(
            "accounting policy audit opinion related party impairment contingency "
            "segment guidance disclosure"
        ),
        top_k=8,
    )

    shared_inputs = {"context": context}
    requests = {
        "main_notes": StructuredPromptRequest(
            system_template=system,
            user_template=(
                "Use only the retrieved context below to extract key notes.\n"
                "Context:\n{context}\n"
                "Return an object: {{'notes': [KeyNote, ...]}}."
            ),
            input_values=shared_inputs,
            output_model=KeyNotesBundle,
        ),
        "audit_notes": StructuredPromptRequest(
            system_template=system,
            user_template=(
                "Focus on governance, audit language, and cautionary disclosures.\n"
                "Context:\n{context}\n"
                "Return an object: {{'notes': [KeyNote, ...]}}."
            ),
            input_values=shared_inputs,
            output_model=KeyNotesBundle,
        ),
    }

    outputs = _call_llm_parallel_structured(
        state,
        requests,
        node_name="extract_key_notes",
    )
    notes: list[KeyNote] = []
    for key in ("main_notes", "audit_notes"):
        bundle = _to_notes_bundle(outputs.get(key))
        notes.extend(bundle.notes)

    notes = _dedupe_notes(notes)
    if not notes:
        notes.append(KeyNote(note_type="other", summary="No notes extracted.", source_refs=_fallback_evidence(state)))

    for note in notes:
        if not note.source_refs:
            note.source_refs = _fallback_evidence(state)

    state.notes = notes
    state.debug["notes_count"] = len(notes)
    log_node(logger, state.doc_meta.doc_id, "extract_key_notes", start_ms)
    return state


def generate_risk_signals(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    pages_text = [page.text for page in state.pages]
    signals = generate_signals(state.statements, state.notes, state.validation_results, pages_text)

    system = _load_prompt("trader_report_prompt.md")
    context = _build_rag_context(
        state,
        query="risk signals cashflow net income working capital disclosure audit",
        top_k=8,
    )

    shared_inputs = {
        "context": context,
        "existing_signals": json.dumps([signal.model_dump(mode="json") for signal in signals], ensure_ascii=False),
        "validation_issues": ",".join(state.validation_results.get("issues", [])),
    }

    requests = {
        "additional_signals": StructuredPromptRequest(
            system_template=system,
            user_template=(
                "Identify additional risk signals from the context and validation issues.\n"
                "Validation issues: {validation_issues}\n"
                "Context:\n{context}\n"
                "Return an object: {{'risk_signals': [RiskSignal, ...]}}."
            ),
            input_values=shared_inputs,
            output_model=RiskSignalsBundle,
        ),
        "signal_explanations": StructuredPromptRequest(
            system_template=system,
            user_template=(
                "Improve explanations for these existing signals while keeping categories grounded in context.\n"
                "Existing signals JSON:\n{existing_signals}\n"
                "Context:\n{context}\n"
                "Return an object: {{'risk_signals': [RiskSignal, ...]}}."
            ),
            input_values=shared_inputs,
            output_model=RiskSignalsBundle,
        ),
    }

    outputs = _call_llm_parallel_structured(
        state,
        requests,
        node_name="generate_risk_signals",
    )

    additional = _to_risk_signals_bundle(outputs.get("additional_signals")).risk_signals
    enriched = _to_risk_signals_bundle(outputs.get("signal_explanations")).risk_signals

    signals = _merge_signals(signals + additional + enriched)
    for signal in signals:
        if not signal.evidence:
            signal.evidence = _fallback_evidence(state)

    state.risk_signals = signals
    state.debug["signals_count"] = len(signals)
    log_node(logger, state.doc_meta.doc_id, "generate_risk_signals", start_ms)
    return state


def build_analysis_context_node(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    state.analysis_context = build_analysis_context_payload(state)
    state.debug["analysis_context_sources"] = len(state.analysis_context.sources)
    state.debug["analysis_context_tokens"] = state.analysis_context.tokens_estimate
    log_node(logger, state.doc_meta.doc_id, "build_analysis_context", start_ms)
    return state


def run_deep_analysis(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    if state.analysis_context is None:
        state.analysis_context = build_analysis_context_payload(state)

    result = _try_hermes_deep_analysis(state)
    if result is None:
        result = _run_llm_deep_analysis(state)

    state.deep_analysis = result
    state.debug["deep_analysis_findings"] = len(result.findings)
    state.debug["deep_analysis_provider"] = result.provider
    log_node(logger, state.doc_meta.doc_id, "run_deep_analysis", start_ms)
    return state


# ---------------------------------------------------------------------------
# Shared helpers (also imported by extraction_nodes and report_nodes)
# ---------------------------------------------------------------------------


def _load_prompt(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _call_llm_structured(
    state: AgentState,
    request: StructuredPromptRequest,
    *,
    node_name: str,
    fallback: Any,
) -> Any:
    client = get_default_llm_client()
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            return client.invoke_structured(
                request,
                run_name=node_name,
                tags=["financial-report-agent", node_name],
                metadata=langsmith_metadata(
                    state.doc_meta.doc_id,
                    node_name,
                    attempt=attempt + 1,
                ),
            )
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        state.errors.append(f"{node_name}_llm_failed:{last_error}")
    return fallback


def _call_llm_parallel_structured(
    state: AgentState,
    requests: dict[str, StructuredPromptRequest],
    *,
    node_name: str,
) -> dict[str, Any]:
    client = get_default_llm_client()
    results: dict[str, Any] = {}
    remaining = dict(requests)

    for attempt in range(2):
        failed: dict[str, StructuredPromptRequest] = {}
        for key, request in remaining.items():
            try:
                results[key] = client.invoke_structured(
                    request,
                    run_name=f"{node_name}.{key}",
                    tags=["financial-report-agent", node_name, "parallel"],
                    metadata=langsmith_metadata(
                        state.doc_meta.doc_id,
                        node_name,
                        attempt=attempt + 1,
                        branch=key,
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "LLM parallel call failed",
                    extra={"key": key, "error": str(exc)},
                )
                failed[key] = request
        if not failed:
            break
        remaining = failed

    if remaining:
        state.errors.append(f"{node_name}_llm_parallel_failed:{list(remaining.keys())}")
    return results


def _build_rag_context(state: AgentState, query: str, *, top_k: int) -> str:
    # Cache the vector index in state.debug to avoid rebuilding on each call
    cached_index = state.debug.get("_rag_index")
    if cached_index is None:
        lang = state.doc_meta.language or "auto"
        cached_index = build_rag_index(state.chunks, state.tables, lang=lang)
        state.debug["_rag_index"] = cached_index

    docs = cached_index.search(query, k=top_k)

    retrieval_debug = state.debug.setdefault("retrieval", {})
    retrieval_debug[query] = {
        "indexed_docs": cached_index.size,
        "returned_docs": len(docs),
    }

    if not docs:
        fallback = "\n".join(chunk.text for chunk in state.chunks[:3])
        return fallback[:4000]

    lines: list[str] = []
    for idx, doc in enumerate(docs, start=1):
        metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
        page = metadata.get("page") or metadata.get("page_start")
        table_id = metadata.get("table_id")
        source_type = metadata.get("source_type", "unknown")
        lines.append(
            f"[Doc {idx}] source_type={source_type} page={page} table_id={table_id}\n"
            f"{doc.page_content[:900]}"
        )
    return "\n\n".join(lines)


def _fallback_evidence(state: AgentState) -> list[SourceRef]:
    if state.pages:
        snippet = state.pages[0].text.strip().split("\n")[0][:200]
        return [SourceRef(ref_type="page_text", page=1, table_id=None, quote=snippet, confidence=0.2)]
    return [SourceRef(ref_type="page_text", page=1, table_id=None, quote="Evidence unavailable", confidence=0.1)]


def _numbers_snapshot(state: AgentState) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for statement in state.statements.values():
        snapshot.update(statement.totals)
    return snapshot


def _llm_statement(state: AgentState, kind: str, *, retry_context: str = "") -> FinancialStatement:
    system = _load_prompt("statement_extraction_prompt.md")
    context = _build_rag_context(
        state,
        query=f"{kind} statement line items totals current prior period",
        top_k=10,
    )

    user_template = (
        "Target statement type: {statement_type}.\n"
        "Use only this context:\n{context}\n"
    )
    input_values: dict[str, str] = {"statement_type": kind, "context": context}

    if retry_context:
        user_template += "{retry_context}\n"
        input_values["retry_context"] = retry_context

    user_template += "Return one FinancialStatement object."

    request = StructuredPromptRequest(
        system_template=system,
        user_template=user_template,
        input_values=input_values,
        output_model=FinancialStatement,
    )

    statement = _call_llm_structured(
        state,
        request,
        node_name="extract_financial_statements",
        fallback=FinancialStatement(
            statement_type=kind,  # type: ignore[arg-type]
            period_end=None,
            period_start=None,
            line_items=[],
            totals={},
            extraction_confidence=0.2,
            issues=["llm_parse_failed"],
        ),
    )

    if not statement.line_items:
        statement.issues.append("no_line_items")
        statement.line_items.append(
            StatementLineItem(
                name_raw="unknown",
                name_norm="unknown",
                value_current=None,
                value_prior=None,
                unit=None,
                currency=None,
                notes="missing_data",
                source_refs=_fallback_evidence(state),
            )
        )
    if statement.statement_type != kind:
        statement.statement_type = kind
    for item in statement.line_items:
        if not item.source_refs:
            item.source_refs = _fallback_evidence(state)
    return statement


# ---------------------------------------------------------------------------
# Deep analysis helpers
# ---------------------------------------------------------------------------


def _try_hermes_deep_analysis(state: AgentState) -> DeepAnalysisResult | None:
    client = get_hermes_agent_client()
    if client is None or state.analysis_context is None:
        return None

    start_ms = monotonic_ms()
    started_at = utc_now()
    provider = "hermes"
    model = os.getenv("HERMES_AGENT_MODEL", "hermes-agent")
    try:
        result = client.analyze(state.analysis_context, task="deep_analysis")
        elapsed_ms = monotonic_ms() - start_ms
        result.doc_id = state.doc_meta.doc_id
        result.provider = result.provider or provider
        result.model = result.model or model
        invocation = ModelInvocation(
            provider=provider,
            model=model,
            task="deep_analysis",
            status="succeeded",
            elapsed_ms=elapsed_ms,
            metadata={"adapter": "hermes_http"},
        )
        result.invocations.append(invocation)
        state.agent_runs.append(
            AgentRun(
                run_id=new_doc_id(),
                doc_id=state.doc_meta.doc_id,
                node_name="run_deep_analysis",
                provider=provider,
                model=model,
                status="succeeded",
                started_at=started_at,
                completed_at=utc_now(),
                elapsed_ms=elapsed_ms,
                metadata={"adapter": "hermes_http"},
            )
        )
        return result
    except Exception as exc:
        elapsed_ms = monotonic_ms() - start_ms
        state.errors.append(f"hermes_deep_analysis_failed:{exc}")
        state.agent_runs.append(
            AgentRun(
                run_id=new_doc_id(),
                doc_id=state.doc_meta.doc_id,
                node_name="run_deep_analysis",
                provider=provider,
                model=model,
                status="failed",
                started_at=started_at,
                completed_at=utc_now(),
                elapsed_ms=elapsed_ms,
                error=str(exc),
                metadata={"adapter": "hermes_http"},
            )
        )
        return None


def _run_llm_deep_analysis(state: AgentState) -> DeepAnalysisResult:
    assert state.analysis_context is not None
    config = get_llm_model_config("deep_analysis")
    start_ms = monotonic_ms()
    started_at = utc_now()
    system = _load_prompt("deep_analysis_prompt.md")
    request = StructuredPromptRequest(
        system_template=system,
        user_template=(
            "Provider metadata: {provider}:{model}\n"
            "Analyze this structured AnalysisContext JSON. Return a DeepAnalysisResult object.\n"
            "AnalysisContext JSON:\n{analysis_context}\n"
        ),
        input_values={
            "provider": config.provider,
            "model": config.model,
            "analysis_context": state.analysis_context.model_dump_json(),
        },
        output_model=DeepAnalysisResult,
    )

    status = "succeeded"
    error: str | None = None
    try:
        result = get_llm_client("deep_analysis").invoke_structured(
            request,
            run_name="run_deep_analysis",
            tags=["financial-report-agent", "deep-analysis"],
            metadata=langsmith_metadata(state.doc_meta.doc_id, "run_deep_analysis"),
        )
    except Exception as exc:
        status = "failed"
        error = str(exc)
        state.errors.append(f"deep_analysis_llm_failed:{exc}")
        result = DeepAnalysisResult(
            doc_id=state.doc_meta.doc_id,
            provider=config.provider,
            model=config.model,
            summary="Deep analysis is unavailable for this run.",
            findings=[],
            limitations=["Deep analysis provider failed; base extraction artifacts remain available."],
        )

    elapsed_ms = monotonic_ms() - start_ms
    result.doc_id = state.doc_meta.doc_id
    result.provider = config.provider
    result.model = config.model
    invocation = ModelInvocation(
        provider=config.provider,
        model=config.model,
        task="deep_analysis",
        status=status,  # type: ignore[arg-type]
        elapsed_ms=elapsed_ms,
        error=error,
        metadata={"source": config.source},
    )
    result.invocations.append(invocation)
    if not result.findings and status == "succeeded":
        result.limitations.append("Deep analysis returned no findings.")
    state.agent_runs.append(
        AgentRun(
            run_id=new_doc_id(),
            doc_id=state.doc_meta.doc_id,
            node_name="run_deep_analysis",
            provider=config.provider,
            model=config.model,
            status=status,  # type: ignore[arg-type]
            started_at=started_at,
            completed_at=utc_now(),
            elapsed_ms=elapsed_ms,
            error=error,
            metadata={"source": config.source},
        )
    )
    return result


# ---------------------------------------------------------------------------
# Validation / conversion helpers
# ---------------------------------------------------------------------------


def _to_notes_bundle(raw: Any) -> KeyNotesBundle:
    if isinstance(raw, KeyNotesBundle):
        return raw
    if isinstance(raw, dict):
        try:
            return KeyNotesBundle.model_validate(raw)
        except ValidationError:
            pass
    if isinstance(raw, list):
        return KeyNotesBundle(notes=_validate_note_list(raw))
    return KeyNotesBundle()


def _to_risk_signals_bundle(raw: Any) -> RiskSignalsBundle:
    if isinstance(raw, RiskSignalsBundle):
        return raw
    if isinstance(raw, dict):
        try:
            return RiskSignalsBundle.model_validate(raw)
        except ValidationError:
            pass
    if isinstance(raw, list):
        return RiskSignalsBundle(risk_signals=_validate_signal_list(raw))
    return RiskSignalsBundle()


def _validate_note_list(raw_items: list[Any]) -> list[KeyNote]:
    notes: list[KeyNote] = []
    for raw in raw_items:
        try:
            notes.append(KeyNote.model_validate(raw))
        except ValidationError:
            continue
    return notes


def _validate_signal_list(raw_items: list[Any]) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    for raw in raw_items:
        try:
            signals.append(RiskSignal.model_validate(raw))
        except ValidationError:
            continue
    return signals


def _dedupe_notes(notes: list[KeyNote]) -> list[KeyNote]:
    deduped: list[KeyNote] = []
    seen: set[tuple[str, str]] = set()
    for note in notes:
        key = (note.note_type, note.summary.strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(note)
    return deduped


def _merge_signals(signals: list[RiskSignal]) -> list[RiskSignal]:
    merged: list[RiskSignal] = []
    by_key: dict[tuple[str, str], int] = {}

    for signal in signals:
        key = (signal.category, signal.title.strip())
        if key not in by_key:
            by_key[key] = len(merged)
            merged.append(signal)
            continue

        idx = by_key[key]
        existing = merged[idx]
        evidence = existing.evidence or []
        if signal.evidence:
            evidence = _merge_evidence(evidence, signal.evidence)
        merged[idx] = RiskSignal(
            signal_id=existing.signal_id,
            category=existing.category,
            title=existing.title,
            severity=_pick_more_severe(existing.severity, signal.severity),  # type: ignore[arg-type]
            description=signal.description if len(signal.description) > len(existing.description) else existing.description,
            metrics={**existing.metrics, **signal.metrics},
            evidence=evidence,
        )
    return merged


def _merge_evidence(base: list[SourceRef], extra: list[SourceRef]) -> list[SourceRef]:
    merged = list(base)
    seen = {(item.ref_type, item.page, item.table_id, item.quote) for item in merged}
    for item in extra:
        key = (item.ref_type, item.page, item.table_id, item.quote)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _pick_more_severe(left: str, right: str) -> str:
    rank = {"low": 1, "medium": 2, "high": 3}
    return left if rank.get(left, 1) >= rank.get(right, 1) else right
