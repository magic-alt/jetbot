from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.schemas.models import DocumentMeta, Page

_MONTH_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"([0-3]?\d),\s*(20\d{2}|19\d{2})\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(20\d{2}|19\d{2})[-/](0?[1-9]|1[0-2])[-/]([0-3]?\d)\b")
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(Inc\.|Corporation|Corp\.|Company|Co\.|Limited|Ltd\.|Holdings|Group|PLC|S\.A\.)(?=$|[\s,])",
    re.IGNORECASE,
)


def enrich_document_meta(meta: DocumentMeta, pages: Sequence[Page | Mapping[str, Any]] | None) -> DocumentMeta:
    text = _pages_text(pages)
    updates: dict[str, Any] = {}
    if not meta.company:
        company = _infer_company(text, meta.filename)
        if company:
            updates["company"] = company
    if not meta.report_type:
        report_type = _infer_report_type(text, meta.filename)
        if report_type:
            updates["report_type"] = report_type
    if meta.period_end is None:
        period_end = _infer_period_end(text, meta.filename)
        if period_end:
            updates["period_end"] = period_end
    return meta.model_copy(update=updates) if updates else meta


def _pages_text(pages: Sequence[Page | Mapping[str, Any]] | None) -> str:
    if not pages:
        return ""
    chunks: list[str] = []
    for page in pages[:3]:
        if isinstance(page, Page):
            chunks.append(page.text)
        elif isinstance(page, Mapping):
            text = page.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def _infer_company(text: str, filename: str) -> str | None:
    for line in _nonempty_lines(text)[:30]:
        cleaned = line.strip(" :\t")
        if len(cleaned) > 80:
            continue
        if _COMPANY_SUFFIX_RE.search(cleaned):
            return cleaned
    name = Path(filename).stem.replace("_", " ").replace("-", " ")
    name = re.sub(
        r"\b(FY\d{2,4}|FY|Q[1-4]|\d{2,4}|annual|quarterly|report|financial|statements|consolidated)\b",
        " ",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if name else None


def _infer_report_type(text: str, filename: str) -> str | None:
    upper = f"{text}\n{filename}".upper()
    if "FORM 10-K" in upper or "ANNUAL REPORT" in upper:
        return "Annual Report"
    if "FORM 10-Q" in upper or "QUARTERLY REPORT" in upper:
        return "Quarterly Report"
    if "CONDENSED CONSOLIDATED" in upper and "STATEMENT" in upper:
        return "Condensed Consolidated Financial Statements"
    if "CONSOLIDATED" in upper and "FINANCIAL" in upper and "STATEMENT" in upper:
        return "Consolidated Financial Statements"
    if "FINANCIAL" in upper and "STATEMENT" in upper:
        return "Financial Statements"
    return None


def _infer_period_end(text: str, filename: str) -> date | None:
    haystack = re.sub(r"\s+", " ", f"{text}\n{filename}")
    month_match = _MONTH_DATE_RE.search(haystack)
    if month_match:
        try:
            return datetime.strptime(month_match.group(0), "%B %d, %Y").date()
        except ValueError:
            return None
    iso_match = _ISO_DATE_RE.search(haystack)
    if iso_match:
        year, month, day = iso_match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None
    return None


def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]