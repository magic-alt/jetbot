from __future__ import annotations

import json
import os
from typing import Any

from src.agent.state import AgentState
from src.finance.utils import table_to_text
from src.llm.token_manager import count_tokens, truncate_to_fit
from src.schemas.models import AnalysisContext, AnalysisContextSource, SourceRef
from src.storage.vector_index import build_rag_index
from src.utils.ids import new_doc_id


_DEFAULT_CONTEXT_TOKEN_BUDGET = 12000
_CONTEXT_QUERIES = [
    "financial performance profitability cash flow balance sheet risk disclosures",
    "accounting policy audit opinion related party impairment contingency segment guidance",
    "revenue net income operating cash flow total assets liabilities equity validation",
]


def build_analysis_context(state: AgentState, *, token_budget: int | None = None) -> AnalysisContext:
    budget = token_budget or int(os.getenv("DEEP_ANALYSIS_CONTEXT_TOKENS", str(_DEFAULT_CONTEXT_TOKEN_BUDGET)))
    sources: list[AnalysisContextSource] = []
    tokens_used = 0

    statement_snapshot = _statement_snapshot(state)
    validation_summary: dict[str, Any] = {
        "issues": state.validation_results.get("issues", []),
        "checks": state.validation_results.get("checks", {}),
        "metrics": state.validation_results.get("metrics", {}),
    }

    tokens_used = _append_source(
        sources,
        tokens_used,
        budget,
        source_type="validation",
        title="Validation summary",
        text=json.dumps(validation_summary, ensure_ascii=False),
        source_refs=_fallback_source_refs(state),
    )
    tokens_used = _append_source(
        sources,
        tokens_used,
        budget,
        source_type="statement",
        title="Statement snapshot",
        text=json.dumps(statement_snapshot, ensure_ascii=False),
        source_refs=_statement_source_refs(state),
    )

    for note in state.notes[:8]:
        tokens_used = _append_source(
            sources,
            tokens_used,
            budget,
            source_type="note",
            title=note.note_type,
            text=note.summary,
            source_refs=note.source_refs,
        )

    for signal in state.risk_signals[:12]:
        tokens_used = _append_source(
            sources,
            tokens_used,
            budget,
            source_type="risk_signal",
            title=f"{signal.category}: {signal.title}",
            text=f"{signal.severity}: {signal.description}\nMetrics: {json.dumps(signal.metrics, ensure_ascii=False)}",
            source_refs=signal.evidence,
        )

    tokens_used = _append_retrieved_sources(state, sources, tokens_used, budget)

    return AnalysisContext(
        doc_id=state.doc_meta.doc_id,
        metadata=state.doc_meta,
        statement_snapshot=statement_snapshot,
        validation_summary=validation_summary,
        sources=sources,
        token_budget=budget,
        tokens_estimate=sum(source.tokens_estimate or 0 for source in sources),
    )


def _statement_snapshot(state: AgentState) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for statement_type, statement in state.statements.items():
        for key, value in statement.totals.items():
            snapshot[f"{statement_type}.{key}"] = value
    return snapshot


def _statement_source_refs(state: AgentState) -> list[SourceRef]:
    refs: list[SourceRef] = []
    seen: set[tuple[str, int, str | None, str | None]] = set()
    for statement in state.statements.values():
        for item in statement.line_items:
            for ref in item.source_refs:
                key = (ref.ref_type, ref.page, ref.table_id, ref.quote)
                if key in seen:
                    continue
                seen.add(key)
                refs.append(ref)
                if len(refs) >= 6:
                    return refs
    return refs or _fallback_source_refs(state)


def _fallback_source_refs(state: AgentState) -> list[SourceRef]:
    if state.pages:
        snippet = state.pages[0].text.strip().split("\n")[0][:200]
        return [SourceRef(ref_type="page_text", page=1, table_id=None, quote=snippet, confidence=0.2)]
    return [SourceRef(ref_type="page_text", page=1, table_id=None, quote="Evidence unavailable", confidence=0.1)]


def _append_retrieved_sources(
    state: AgentState,
    sources: list[AnalysisContextSource],
    tokens_used: int,
    budget: int,
) -> int:
    if not state.chunks and not state.tables:
        return tokens_used

    lang = state.doc_meta.language or "auto"
    # Reuse cached RAG index from state.debug if available
    rag_index = state.debug.get("_rag_index")
    if rag_index is None:
        rag_index = build_rag_index(state.chunks, state.tables, lang=lang)
        state.debug["_rag_index"] = rag_index
    index = rag_index
    seen: set[tuple[str, str]] = set()
    for query in _CONTEXT_QUERIES:
        for document in index.search(query, k=6):
            metadata = document.metadata if isinstance(document.metadata, dict) else {}
            source_type = "table" if metadata.get("source_type") == "table" else "page_text"
            key = (source_type, str(metadata.get("table_id") or metadata.get("chunk_id") or document.page_content[:80]))
            if key in seen:
                continue
            seen.add(key)

            title = str(metadata.get("title") or metadata.get("section") or source_type)
            tokens_used = _append_source(
                sources,
                tokens_used,
                budget,
                source_type=source_type,
                title=title,
                text=document.page_content,
                source_refs=[_source_ref_from_metadata(metadata, document.page_content)],
            )
            if tokens_used >= budget:
                return tokens_used

    for table in state.tables[:4]:
        tokens_used = _append_source(
            sources,
            tokens_used,
            budget,
            source_type="table",
            title=table.title or table.table_id,
            text=table.raw_markdown or table_to_text(table),
            source_refs=table.source_refs,
        )
        if tokens_used >= budget:
            break
    return tokens_used


def _source_ref_from_metadata(metadata: dict[str, Any], text: str) -> SourceRef:
    source_type = metadata.get("source_type")
    page = metadata.get("page") or metadata.get("page_start") or 1
    if source_type == "table":
        return SourceRef(
            ref_type="table",
            page=int(page),
            table_id=metadata.get("table_id"),
            quote=text.strip().split("\n")[0][:200],
            confidence=0.55,
        )
    return SourceRef(
        ref_type="page_text",
        page=int(page),
        table_id=None,
        quote=text.strip().split("\n")[0][:200],
        confidence=0.4,
    )


def _append_source(
    sources: list[AnalysisContextSource],
    tokens_used: int,
    budget: int,
    *,
    source_type: str,
    title: str | None,
    text: str,
    source_refs: list[SourceRef],
) -> int:
    content = text.strip()
    if not content or tokens_used >= budget:
        return tokens_used

    remaining = max(budget - tokens_used, 0)
    truncated = truncate_to_fit(content, remaining + 256, reserve_output=256)
    estimate = count_tokens(truncated)
    if estimate <= 0:
        return tokens_used

    sources.append(
        AnalysisContextSource(
            source_id=new_doc_id(),
            source_type=source_type,  # type: ignore[arg-type]
            title=title,
            text=truncated,
            source_refs=source_refs,
            tokens_estimate=estimate,
        )
    )
    return min(tokens_used + estimate, budget)