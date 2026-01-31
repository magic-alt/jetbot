# Financial Report PDF Agent

This repository provides a FastAPI service and CLI for parsing financial report PDFs, extracting structured statements and notes, running validation checks, and generating a trader-style report with evidence references. It runs in mock mode by default and can use an OpenAI model when configured.

## Quick Start (Mock Mode)

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .
make dev
```

Upload a PDF and trigger analysis (mock LLM if `OPENAI_API_KEY` is not set).

## Configure OpenAI

1. Copy `.env.example` to `.env`
2. Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL`
3. Restart the API or CLI

## API Examples

```bash
curl -F "file=@path/to/report.pdf" http://localhost:8000/v1/documents
curl -X POST http://localhost:8000/v1/documents/<doc_id>/analyze
curl http://localhost:8000/v1/documents/<doc_id>/report.md
```

## CLI Examples

```bash
python -m src.cli analyze --pdf path/to/report.pdf --out data --company "Example Co" --period-end 2025-12-31
python -m src.cli show --doc-id <doc_id> --what report
```

## Output Files

Results are stored under `data/{doc_id}/`:

- `raw.pdf`: uploaded PDF
- `extracted/pages.json`, `tables.json`, `statements.json`, `notes.json`, `risk_signals.json`
- `report/trader_report.json`, `report/trader_report.md`

## Not Financial Advice

This system provides structured extraction and analytical signals only. It does not provide investment advice or recommend trades.
