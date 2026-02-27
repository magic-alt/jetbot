from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

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
            data = _mock_statement(prompt)
        elif "keynote" in prompt or "notes" in prompt:
            data = _mock_notes()
        elif "traderreport" in prompt or "trader report" in prompt:
            data = _mock_report()
        elif "risksignal" in prompt or "risk signal" in prompt:
            data = _mock_risk_signals()
        else:
            data = {"ok": True}
        return json.dumps(data, ensure_ascii=True)

    def invoke_structured(
        self,
        request: Any,
        *,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        del run_name, tags, metadata
        prompt = f"{request.system_template}\n{request.user_template}".lower()
        if "statement" in prompt or "financialstatement" in prompt:
            data: Any = _mock_statement(prompt)
        elif "key note" in prompt or "notes" in prompt:
            data = _mock_notes()
        elif "risk signal" in prompt or "risksignal" in prompt:
            data = _mock_risk_signals()
        elif "trader report" in prompt or "traderreport" in prompt:
            data = _mock_report()
        else:
            data = {"ok": True}
        return _coerce_output(data, request.output_model)

    def invoke_parallel(
        self,
        requests: dict[str, Any],
        *,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            key: self.invoke_structured(
                request,
                run_name=f"{run_name}.{key}" if run_name else key,
                tags=tags,
                metadata=metadata,
            )
            for key, request in requests.items()
        }


def _mock_evidence() -> list[dict[str, object]]:
    ref = SourceRef(ref_type="page_text", page=1, table_id=None, quote="mock evidence", confidence=0.2)
    return [ref.model_dump()]


def _mock_statement(prompt: str = "") -> dict[str, object]:
    prompt_lower = prompt.lower()
    if "income" in prompt_lower or "profit" in prompt_lower:
        statement = FinancialStatement(
            statement_type="income",
            line_items=[],
            totals={"revenue": 0.0, "net_income": 0.0, "cost_of_goods_sold": 0.0},
            extraction_confidence=0.2,
            issues=["mock_statement"],
        )
    elif "cashflow" in prompt_lower or "cash flow" in prompt_lower:
        statement = FinancialStatement(
            statement_type="cashflow",
            line_items=[],
            totals={"operating_cf": 0.0},
            extraction_confidence=0.2,
            issues=["mock_statement"],
        )
    else:
        statement = FinancialStatement(
            statement_type="balance",
            line_items=[],
            totals={"total_assets": 0.0, "total_liabilities": 0.0, "total_equity": 0.0},
            extraction_confidence=0.2,
            issues=["mock_statement"],
        )
    return statement.model_dump()


def _mock_notes() -> dict[str, object]:
    note = KeyNote(note_type="accounting_policy", summary="mock note", source_refs=_mock_evidence())
    return {"notes": [note.model_dump()]}


def _mock_risk_signals() -> dict[str, object]:
    signal = RiskSignal(
        signal_id="mock-1",
        category="other",
        title="Mock risk",
        severity="low",
        description="Mock signal for testing.",
        metrics={},
        evidence=_mock_evidence(),
    )
    return {"risk_signals": [signal.model_dump()]}


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
    return report.model_dump(mode="json")


def _coerce_output(data: Any, output_model: Any) -> Any:
    if output_model is None:
        return data
    try:
        return output_model.model_validate(data)
    except ValidationError:
        if isinstance(data, list):
            field_names = list(output_model.model_fields.keys())
            if len(field_names) == 1:
                wrapped = {field_names[0]: data}
                return output_model.model_validate(wrapped)
        if isinstance(data, dict):
            patched = dict(data)
            for field_name, field_info in output_model.model_fields.items():
                annotation = field_info.annotation
                if getattr(annotation, "__origin__", None) is list and field_name not in patched:
                    patched[field_name] = []
            return output_model.model_validate(patched)
        raise
