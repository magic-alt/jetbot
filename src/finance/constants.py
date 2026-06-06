"""Shared constants for financial analysis."""
from __future__ import annotations

# Keywords for detecting financial statement type from table headers/content.
# Used by extraction_nodes._detect_statement_type
STATEMENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "income": [
        "利润表", "损益表", "income statement", "profit and loss",
        "statement of operations",
        "营业收入", "revenue", "net income", "净利润",
    ],
    "balance": [
        "资产负债表", "balance sheet", "statement of financial position",
        "资产总计", "total assets", "负债合计", "total liabilities",
    ],
    "cashflow": [
        "现金流量表", "cash flow statement", "statement of cash flows",
        "cash flow",
        "经营活动", "operating activities", "投资活动", "investing activities",
    ],
}

# Keywords for audit opinion and governance signal detection.
# Used by finance/signals.py
AUDIT_KEYWORDS: list[str] = [
    "保留意见", "无法表示意见", "否定意见", "持续经营",
    "qualified opinion", "adverse opinion", "disclaimer of opinion",
    "going concern", "material uncertainty",
]

# Default currency mapping by document language.
CURRENCY_BY_LANGUAGE: dict[str, str] = {
    "zh": "CNY",
    "cn": "CNY",
    "en": "USD",
    "default": "CNY",
}

# Default unit mapping by document language.
UNIT_BY_LANGUAGE: dict[str, str] = {
    "zh": "万元",
    "cn": "万元",
    "en": "USD millions",
    "default": "万元",
}
