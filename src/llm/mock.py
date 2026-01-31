from __future__ import annotations

import json

from src.schemas.models import (
    FinancialStatement,
    KeyNote,
    RiskSignal,
    SourceRef,
    TraderReport,
)


class MockLLMClient:
    async def chat(self, system: str, user: str, json_schema: dict | None = None) -> str:
        prompt = f"{system}\n{user}".lower()
        if "statement" in prompt or "financialstatement" in prompt:
            data = _mock_statement()
        elif "keynote" in prompt or "notes" in prompt:
            data = _mock_notes()
        elif "traderreport" in prompt or "trader report" in prompt:
            data = _mock_report()
        elif "risksignal" in prompt or "risk signal" in prompt:
            data = _mock_risk_signals()
        else:
            data = {"ok": True}
        return json.dumps(data, ensure_ascii=True)


def _mock_evidence() -> list[dict[str, object]]:
    ref = SourceRef(ref_type="page_text", page=1, table_id=None, quote="mock evidence", confidence=0.2)
    return [ref.model_dump()]


def _mock_statement() -> dict[str, object]:
    statement = FinancialStatement(
        statement_type="balance",
        line_items=[],
        totals={"total_assets": 0.0, "total_liabilities": 0.0, "total_equity": 0.0},
        extraction_confidence=0.2,
        issues=["mock_statement"],
    )
    return statement.model_dump()


def _mock_notes() -> list[dict[str, object]]:
    note = KeyNote(note_type="accounting_policy", summary="mock note", source_refs=_mock_evidence())
    return [note.model_dump()]


def _mock_risk_signals() -> list[dict[str, object]]:
    signal = RiskSignal(
        signal_id="mock-1",
        category="other",
        title="Mock risk",
        severity="low",
        description="Mock signal for testing.",
        metrics={},
        evidence=_mock_evidence(),
    )
    return [signal.model_dump()]


def _mock_report() -> dict[str, object]:
    report = TraderReport(
        doc_id="mock",
        executive_summary="Mock executive summary.",
        key_drivers=["Mock driver"],
        numbers_snapshot={},
        risk_signals=[],
        notes=[],
        limitations=["Mock output; no model configured."],
    )
    return report.model_dump()
