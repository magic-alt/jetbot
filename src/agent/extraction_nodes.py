"""Financial statement extraction and validation pipeline nodes."""
from __future__ import annotations

import json
import re

from src.agent.analysis_nodes import _llm_statement
from src.agent.state import AgentState
from src.finance.constants import (
    CURRENCY_BY_LANGUAGE,
    STATEMENT_TYPE_KEYWORDS,
    UNIT_BY_LANGUAGE,
)
from src.finance.facts import facts_from_statements
from src.finance.normalizer import normalize_account_name
from src.finance.utils import table_rows
from src.finance.validators import validate_facts, validate_statements
from src.schemas.models import (
    FinancialStatement,
    Page,
    SourceRef,
    StatementLineItem,
    Table,
)
from src.utils.logging import get_logger, log_node
from src.utils.time import monotonic_ms


logger = get_logger(__name__)


def extract_financial_statements(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    statements: dict[str, FinancialStatement] = {}
    tables_by_type: dict[str, list[Table]] = {"balance": [], "income": [], "cashflow": []}

    # Build retry context from previous validation failures
    retry_context = ""
    if state.retry_count > 0 and state.validation_results:
        prev_issues = state.validation_results.get("issues", [])
        prev_checks = state.validation_results.get("checks", {})
        if prev_issues:
            retry_context = (
                f"IMPORTANT: Previous extraction attempt failed validation "
                f"(retry {state.retry_count}). Issues found: {', '.join(prev_issues)}. "
                f"Checks: {json.dumps(prev_checks)}. "
                f"Please pay extra attention to these problems and ensure "
                f"totals are consistent (assets = liabilities + equity), "
                f"units are uniform, and all key fields are populated."
            )

    for table in state.tables:
        kind = _detect_statement_type(table)
        if kind:
            tables_by_type[kind].append(table)

    for kind, tables in tables_by_type.items():
        if tables:
            statements[kind] = _tables_to_statement(kind, tables)

    missing = [k for k in ("income", "balance", "cashflow") if k not in statements]
    if missing:
        for kind in missing:
            text_statement = _statement_from_pages(state, kind)
            statements[kind] = text_statement if text_statement.line_items else _llm_statement(state, kind, retry_context=retry_context)

    state.statements = statements
    state.debug["statement_types"] = list(statements.keys())
    log_node(logger, state.doc_meta.doc_id, "extract_financial_statements", start_ms)
    return state


def validate_and_reconcile(state: AgentState) -> AgentState:
    start_ms = monotonic_ms()
    if not state.facts:
        state.facts = facts_from_statements(state.doc_meta, state.statements)
    state.validation_results = validate_statements(state.statements)
    state.fact_validation_results = validate_facts(state.doc_meta, state.facts, state.statements)
    severe = any(
        issue in {"balance_equation_failed", "balance_missing_totals"} or issue.startswith("unit_mismatch")
        for issue in state.validation_results.get("issues", [])
    )
    severe = severe or any(issue.severity == "high" for issue in (state.fact_validation_results.issues if state.fact_validation_results else []))
    # Remove any previous validation_failed entries before deciding, ensuring idempotency
    state.errors = [err for err in state.errors if err != "validation_failed"]
    if severe:
        state.errors.append("validation_failed")
        state.retry_count += 1
    log_node(logger, state.doc_meta.doc_id, "validate_and_reconcile", start_ms)
    return state


def _detect_statement_type(table: Table) -> str | None:
    # Check table title first (cheapest check)
    if table.title:
        title_lower = table.title.lower()
        for kind, keywords in STATEMENT_TYPE_KEYWORDS.items():
            if any(kw in title_lower for kw in keywords):
                return kind

    # Fall back to checking only the first few rows of cells
    n_cols = table.n_cols or 1
    max_cells = n_cols * 3  # first 3 rows
    header_cells = table.cells[:max_cells] if len(table.cells) > max_cells else table.cells
    text = " ".join(cell.text for cell in header_cells).lower()

    for kind, keywords in STATEMENT_TYPE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return kind
    return None


def _tables_to_statement(kind: str, tables: list[Table]) -> FinancialStatement:
    line_items: list[StatementLineItem] = []
    totals: dict[str, float] = {}
    for table in tables:
        rows = table_rows(table)
        for row in rows:
            if not row:
                continue
            name_raw = row[0]
            value_current = _parse_number(row[1]) if len(row) > 1 else None
            value_prior = _parse_number(row[2]) if len(row) > 2 else None
            name_norm = normalize_account_name(name_raw)
            item = StatementLineItem(
                name_raw=name_raw,
                name_norm=name_norm,
                value_current=value_current,
                value_prior=value_prior,
                unit=None,
                currency=None,
                notes=None,
                source_refs=list(table.source_refs),
            )
            line_items.append(item)
            if name_norm in {
                "total_assets",
                "total_liabilities",
                "total_equity",
                "cash_and_equivalents",
                "revenue",
                "gross_profit",
                "operating_income",
                "net_income",
                "operating_cf",
                "capex",
            } and value_current is not None:
                totals[name_norm] = value_current
    return FinancialStatement(
        statement_type=kind,  # type: ignore[arg-type]
        period_end=None,
        period_start=None,
        line_items=line_items,
        totals=totals,
        extraction_confidence=0.65,
        issues=[],
    )


def _statement_from_pages(state: AgentState, kind: str) -> FinancialStatement:
    labels: dict[str, list[tuple[str, str, int]]] = {
        "income": [
            ("Revenue", "revenue", 2),
            ("Total net sales", "revenue", 2),
            ("Net sales", "revenue", 2),
            ("营业收入", "revenue", 2),
            ("Total cost of sales", "cost_of_goods_sold", 2),
            ("Cost of goods sold", "cost_of_goods_sold", 2),
            ("营业成本", "cost_of_goods_sold", 2),
            ("Gross margin", "gross_profit", 2),
            ("Gross Profit", "gross_profit", 2),
            ("毛利润", "gross_profit", 2),
            ("Operating profit", "operating_income", 2),
            ("Operating income", "operating_income", 2),
            ("营业利润", "operating_income", 2),
            ("Net income", "net_income", 2),
            ("净利润", "net_income", 2),
        ],
        "balance": [
            ("Cash and equivalents", "cash_and_equivalents", 0),
            ("Cash and cash equivalents", "cash_and_equivalents", 0),
            ("货币资金", "cash_and_equivalents", 0),
            ("Total Assets", "total_assets", 0),
            ("Total assets", "total_assets", 0),
            ("资产总计", "total_assets", 0),
            ("Total Liabilities", "total_liabilities", 0),
            ("Total liabilities", "total_liabilities", 0),
            ("负债合计", "total_liabilities", 0),
            ("Total Equity", "total_equity", 0),
            ("Total shareholders\u2019 equity", "total_equity", 0),
            ("Total shareholders' equity", "total_equity", 0),
            ("所有者权益合计", "total_equity", 0),
            ("Total liabilities and shareholders\u2019 equity", "total_liabilities_and_equity", 0),
            ("Total liabilities and shareholders' equity", "total_liabilities_and_equity", 0),
        ],
        "cashflow": [
            ("Cash flow from operations", "operating_cf", 0),
            ("Cash generated by operating activities", "operating_cf", 0),
            ("Net cash provided by operating activities", "operating_cf", 0),
            ("经营活动产生的现金流量净额", "operating_cf", 0),
            ("Capital expenditures", "capex", 0),
            ("购建固定资产、无形资产和其他长期资产支付的现金", "capex", 0),
            ("Cash generated by investing activities", "investing_cf", 0),
            ("Cash used in financing activities", "financing_cf", 0),
        ],
    }

    lang = state.doc_meta.language or "default"
    default_unit = UNIT_BY_LANGUAGE.get(lang, UNIT_BY_LANGUAGE["default"])
    default_currency = CURRENCY_BY_LANGUAGE.get(lang, CURRENCY_BY_LANGUAGE["default"])

    line_items: list[StatementLineItem] = []
    totals: dict[str, float] = {}
    seen: set[str] = set()
    segment_boundaries = [label for label, _, _ in labels.get(kind, [])]
    if kind == "income":
        segment_boundaries.extend(["Operating expenses", "营业费用"])
    for label, name_norm, preferred_index in labels.get(kind, []):
        if name_norm in seen:
            continue
        match = _extract_labeled_metric(state.pages, label, preferred_index, segment_boundaries)
        if match is None:
            continue
        value, source_ref = match
        line_items.append(
            StatementLineItem(
                name_raw=label,
                name_norm=name_norm,
                value_current=value,
                value_prior=None,
                unit=default_unit,
                currency=default_currency,
                notes="text_extracted",
                source_refs=[source_ref],
            )
        )
        totals[name_norm] = value
        seen.add(name_norm)

    return FinancialStatement(
        statement_type=kind,  # type: ignore[arg-type]
        period_end=state.doc_meta.period_end,
        period_start=None,
        line_items=line_items,
        totals=totals,
        extraction_confidence=0.7 if line_items else 0.0,
        issues=[] if line_items else ["text_metrics_not_found"],
    )


def _extract_labeled_metric(
    pages: list[Page],
    label: str,
    preferred_index: int,
    known_labels: list[str],
) -> tuple[float, SourceRef] | None:
    label_lower = label.lower()
    for page in pages:
        normalized_text = " ".join(page.text.split())
        offset = normalized_text.lower().find(label_lower)
        if offset < 0:
            continue
        snippet = normalized_text[offset : offset + 260]
        segment = _metric_segment(snippet, label, known_labels)
        values = _parse_numbers_from_snippet(segment)
        if not values:
            continue
        value = _select_metric_value(values, preferred_index)
        return value, SourceRef(ref_type="page_text", page=page.page_number, table_id=None, quote=segment, confidence=0.65)
    return None


def _metric_segment(snippet: str, label: str, known_labels: list[str]) -> str:
    snippet_lower = snippet.lower()
    search_start = len(label)
    next_label_offsets = [
        position
        for candidate in known_labels
        if candidate.lower() != label.lower()
        for position in [snippet_lower.find(candidate.lower(), search_start)]
        if position >= 0
    ]
    if not next_label_offsets:
        return snippet
    return snippet[: min(next_label_offsets)].rstrip()


def _select_metric_value(values: list[float], preferred_index: int) -> float:
    if preferred_index <= 0 or len(values) <= 2:
        return values[0]
    return values[min(preferred_index, len(values) - 1)]


def _parse_numbers_from_snippet(snippet: str) -> list[float]:
    text = re.sub(r"\(\d+\)", "", snippet)
    values: list[float] = []
    for token in re.findall(r"\(?\$?\s*[\-－]?\d[\d,]*(?:\.\d+)?\)?", text):
        value = _parse_number(token)
        if value is not None:
            values.append(value)
    return values


_UNIT_MULTIPLIERS = {
    "万元": 1e4,
    "亿元": 1e8,
    "百万": 1e6,
    "千万": 1e7,
    "万": 1e4,
    "亿": 1e8,
}

# Characters that indicate negative values in Chinese financial reports
_NEGATIVE_MARKERS = re.compile(r"^[△▲\-－]")


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.replace(",", "").replace(" ", "").strip()
    if not text:
        return None

    # Handle parenthetical negatives: (1234.56) or （1234.56）
    negative = False
    if (text.startswith("(") and text.endswith(")")) or (text.startswith("（") and text.endswith("）")):
        negative = True
        text = text[1:-1].strip()

    # Handle leading negative markers: △, ▲, -, －
    if not negative and _NEGATIVE_MARKERS.match(text):
        negative = True
        text = _NEGATIVE_MARKERS.sub("", text).strip()

    # Strip percentage sign (return as decimal proportion)
    is_percent = False
    if text.endswith("%") or text.endswith("％"):
        is_percent = True
        text = text[:-1].strip()

    # Strip currency symbols
    text = text.lstrip("$¥￥€£＄")

    # Check for Chinese unit suffixes and apply multiplier
    multiplier = 1.0
    for unit, mult in _UNIT_MULTIPLIERS.items():
        if text.endswith(unit):
            multiplier = mult
            text = text[: -len(unit)].strip()
            break

    try:
        num = float(text)
    except ValueError:
        return None

    if is_percent:
        num /= 100.0

    num *= multiplier
    return -num if negative else num
