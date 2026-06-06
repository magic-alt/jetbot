from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import typer
from dotenv import load_dotenv

from src.agent.graph import build_graph
from src.agent.state import AgentState
from src.schemas.models import DocumentMeta
from src.storage.local_store import LocalStore
from src.utils.ids import new_doc_id

app = typer.Typer(help="Financial report PDF analysis CLI")
load_dotenv()


@app.command()
def analyze(
    pdf: str = typer.Option(..., help="Path to PDF file"),
    out: str = typer.Option("data", help="Output directory"),
    company: str | None = typer.Option(None, help="Company name"),
    ticker: str | None = typer.Option(None, help="Ticker symbol"),
    cik: str | None = typer.Option(None, help="CIK identifier"),
    filing_type: str | None = typer.Option(None, help="Filing type (for example 10-K or 10-Q)"),
    period_end: str | None = typer.Option(None, help="Report period end (YYYY-MM-DD)"),
    report_type: str | None = typer.Option(None, help="Report type"),
    language: str | None = typer.Option(None, help="Language"),
):
    doc_id = new_doc_id()
    store = LocalStore(out)
    pdf_path = Path(pdf)
    if not pdf_path.exists():
        raise typer.BadParameter("PDF path not found")
    store.save_raw_pdf(doc_id, str(pdf_path))

    parsed_period = date.fromisoformat(period_end) if period_end else None
    meta = DocumentMeta(
        doc_id=doc_id,
        filename=pdf_path.name,
        company=company,
        ticker=ticker,
        cik=cik,
        filing_type=filing_type,
        period_end=parsed_period,
        report_type=report_type,
        language=language,
    )
    store.save_meta(doc_id, meta)

    state = AgentState(doc_meta=meta, pdf_path=str(store.doc_dir(doc_id) / "raw.pdf"), data_dir=out)
    graph = build_graph()
    graph.invoke(state.model_dump())

    report_path = Path(out) / doc_id / "report" / "trader_report.md"
    typer.echo(f"Analysis complete. Report: {report_path}")


@app.command("render-report")
def render_report(doc_id: str, out: str = "data"):
    path = Path(out) / doc_id / "report" / "trader_report.md"
    if not path.exists():
        raise typer.BadParameter("Report not found")
    typer.echo(path)


@app.command()
def show(doc_id: str, what: str = typer.Option("report", help="report|signals|statements"), out: str = "data"):
    store = LocalStore(out)
    mapping = {
        "report": "report/trader_report.json",
        "signals": "extracted/risk_signals.json",
        "statements": "extracted/statements.json",
    }
    if what not in mapping:
        raise typer.BadParameter("Invalid --what value")
    data = store.load_json(doc_id, mapping[what])
    if data is None:
        raise typer.BadParameter("Requested data not found")
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@app.command("export-facts")
def export_facts(
    doc_id: str = typer.Argument(..., help="Document ID to export"),
    out: str = typer.Option("data", help="Data directory"),
    output_file: str | None = typer.Option(None, "--output", "-o", help="Write JSON to file instead of stdout"),
    effective: bool = typer.Option(True, help="Apply user corrections before export"),
):
    """Export normalised financial facts for downstream consumption.

    Produces a JSON envelope with the five core metrics (revenue_growth,
    net_profit_growth, gross_margin, operating_cash_flow, debt_ratio)
    that quantitative platforms can ingest as fundamental-factor input.
    """
    from src.export.builder import build_export
    from src.finance.facts import apply_corrections
    from src.schemas.models import Correction, FinancialFact, FinancialStatement, RiskSignal

    store = LocalStore(out)

    meta_raw = store.load_json(doc_id, "meta.json")
    if meta_raw is None:
        raise typer.BadParameter(f"Document {doc_id} not found")
    meta = DocumentMeta.model_validate(meta_raw)

    # Load statements
    stmts_raw = store.load_json(doc_id, "extracted/statements.json") or {}
    statements: dict[str, FinancialStatement] = {}
    for key, val in stmts_raw.items():
        try:
            statements[key] = FinancialStatement.model_validate(val)
        except Exception:
            continue

    # Load facts
    facts_raw = store.load_json(doc_id, "extracted/facts.json") or []
    facts = [FinancialFact.model_validate(f) for f in facts_raw if isinstance(f, dict)]

    if effective:
        corrections_raw = store.load_json(doc_id, "extracted/corrections.json") or []
        corrections = [Correction.model_validate(c) for c in corrections_raw if isinstance(c, dict)]
        if corrections:
            facts = apply_corrections(facts, corrections)

    # Load risk signals
    signals_raw = store.load_json(doc_id, "extracted/risk_signals.json") or []
    risk_signals = [RiskSignal.model_validate(s) for s in signals_raw if isinstance(s, dict)]

    envelope = build_export(
        meta=meta,
        statements=statements,
        facts=facts,
        risk_signals=risk_signals,
        corrections_applied=effective,
    )
    result = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False, indent=2)

    if output_file:
        Path(output_file).write_text(result, encoding="utf-8")
        typer.echo(f"Export written to {output_file}")
    else:
        typer.echo(result)


if __name__ == "__main__":
    app()
