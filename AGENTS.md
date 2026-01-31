# Repository Guidelines

This repository implements a financial-report PDF parsing and analysis agent. It targets a Python 3.11+ stack with FastAPI, LangGraph, PyMuPDF/pdfplumber, and Pydantic v2. Keep changes focused on the MVP pipeline and ensure all analysis outputs are traceable to source evidence.

## Project Structure & Module Organization

- `src/api/`: FastAPI app, routes, and response envelopes.
- `src/agent/`: LangGraph workflow (`graph.py`, `nodes.py`, `state.py`).
- `src/pdf/`: PDF ingestion, table extraction, OCR stubs, rendering.
- `src/finance/`: schemas, normalization, validators, risk signals.
- `src/llm/`: LLM abstraction + mock and OpenAI clients.
- `src/prompts/`: prompt templates for extraction and reporting.
- `src/storage/`: local JSON/SQLite storage and task tracking.
- `src/utils/`: logging, IDs, time helpers.
- `tests/`: pytest unit tests and pipeline mock tests.
- `data/`: runtime outputs (ignored by git).

## Build, Test, and Development Commands

- `make dev`: start the API service locally (preferred).
- `uvicorn src.api.main:app --reload`: alternative dev server.
- `python -m src.cli analyze --pdf path/to.pdf --out data/`: run the CLI pipeline.
- `python -m pytest`: run unit tests.

## Coding Style & Naming Conventions

- Python: 4-space indentation, type hints required for public functions.
- Pydantic v2 models live under `src/schemas/` or `src/finance/`.
- Use `snake_case` for functions/variables and `PascalCase` for classes.
- Log with `doc_id`, `node_name`, and `elapsed_ms` for each node.

## Testing Guidelines

- Use pytest; target validators, schema validation, and signal rules.
- Prefer deterministic tests with mock LLM/PDF extractors.
- Name tests `test_<area>_<behavior>.py` and keep fixtures under `tests/fixtures/`.

## Commit & Pull Request Guidelines

- No established commit style found in this repo; use concise, imperative messages (e.g., “add validator for balance check”).
- PRs should include: purpose, scope, test commands run, and sample outputs (report JSON/MD) if behavior changes.

## Security & Configuration Tips

- Secrets in `.env` only; do not commit API keys.
- Keep all analysis outputs with `SourceRef` evidence (page/table/quote).
- If LLM output fails validation, retry once and downgrade confidence.
