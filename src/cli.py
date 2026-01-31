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
    store = LocalStore(out)
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


if __name__ == "__main__":
    app()
