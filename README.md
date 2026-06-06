# Jetbot

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/magic-alt/jetbot/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/magic-alt/jetbot/actions/workflows/ci.yml)
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker)](https://github.com/magic-alt/jetbot/pkgs/container/jetbot)

Jetbot is a Filing-to-Model Copilot and Financial Fact Platform for evidence-backed financial report extraction. It turns PDF filings into canonical financial facts, structured statements, key notes, risk signals, event-study outputs, and analyst-ready summaries.

It is designed for teams that need a single workflow to ingest reports, inspect source evidence, review and correct extracted facts, and ship the results through an API, a CLI, exports, or a browser UI.

## Highlights

- End-to-end PDF pipeline for raw text, tables, statements, notes, facts, and report generation.
- Canonical financial fact layer with page/table/cell evidence metadata for review and downstream exports.
- Evaluation runner with machine-readable reports and configurable quality thresholds.
- Works in mock mode out of the box, with optional OpenAI and Anthropic model routing.
- Vue 3 dashboard for reviewing original PDFs alongside extraction and analysis outputs.
- Docker-first local stack with API, worker, Redis, PostgreSQL, and MinIO.
- Pluggable storage, retrieval, tracing, and market-data integrations.
- Production-friendly defaults for auth, rate limiting, metrics, and tracing.

## Architecture

```mermaid
flowchart LR
  A[Financial Filing PDF] --> B[PDF extraction and OCR]
  B --> C[Statements and canonical facts]
  C --> D[Evidence and validation]
  D --> E[Review, API, and exports]
  D --> F[Risk signals and analyst reports]
  E --> G[Vue dashboard at /ui]
  F --> G
```

## Quick Start

### Option 1: Local development

Use this path when you want the fastest edit-run loop.

```bash
python -m venv .venv
# activate the virtual environment for your shell
pip install -e .
make dev
```

The API starts at `http://127.0.0.1:8000`.

If you want the Vue frontend in dev mode as well:

```bash
make web-install
make web-dev
```

The Vite app runs at `http://127.0.0.1:5173` and proxies API requests to the local backend.

### Option 2: Full Docker stack

Use this path when you want the full local system with background worker and infrastructure services.

```bash
copy .env.example .env
make docker-up
```

`make docker-up` now does four things in one flow:

- builds the backend image with the Vue production bundle included
- starts the API, worker, Redis, PostgreSQL, and MinIO services
- waits until the API health endpoint is ready
- opens the frontend automatically at `http://127.0.0.1:18000/ui/`

Set `JETBOT_OPEN_BROWSER=0` if you want to skip the automatic browser launch.

Stop the stack with:

```bash
make docker-down
```

## What You Get

After startup, the main entry points are:

| Surface | URL / Command | Notes |
| --- | --- | --- |
| Web UI | `http://127.0.0.1:18000/ui/` | Review uploaded PDFs, tables, statements, signals, and generated reports |
| API | `http://127.0.0.1:18000/v1` | Programmatic ingestion and retrieval, including canonical facts |
| OpenAPI docs | `http://127.0.0.1:18000/docs` | Interactive API explorer |
| Health | `http://127.0.0.1:18000/health` | Liveness probe |
| Metrics | `http://127.0.0.1:18000/metrics` | Prometheus endpoint |
| CLI | `python -m src.cli --help` | Local automation and scripting |

## Common Workflows

### Analyze a PDF from the CLI

```bash
python -m src.cli analyze --pdf path/to/report.pdf --out data --company "Example Co" --period-end 2025-12-31
```

### Run the bundled real-PDF example

```bash
python examples/apple_10k_analysis/run_example.py
```

### Call the API directly

```bash
curl -F "file=@path/to/report.pdf" \
  -H "X-API-Key: your-key" \
  http://127.0.0.1:18000/v1/documents

curl -X POST \
  -H "X-API-Key: your-key" \
  http://127.0.0.1:18000/v1/documents/<doc_id>/analyze
```

## Configuration

Jetbot starts in mock mode if no provider key is configured. Most teams only need a small set of environment variables to get productive:

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Enable OpenAI-backed extraction and reporting | empty |
| `ANTHROPIC_API_KEY` | Enable Anthropic-backed models | empty |
| `LLM_DEFAULT_MODEL` | Default router target in `provider:model` format | empty |
| `LLM_EXTRACTION_MODEL` | Override the extraction model | empty |
| `LLM_REPORT_MODEL` | Override the reporting model | empty |
| `RAG_MODE` | Retrieval mode: `token_overlap`, `embedding`, `hybrid` | `token_overlap` |
| `TASK_BACKEND` | `background` or `celery` | `background` |
| `STORAGE_BACKEND` | `local` or `postgres` | `local` |
| `API_KEYS` | Comma-separated API keys; blank disables auth | empty |

Docker host ports are fixed to `18000` (API/UI), `16379` (Redis), `15432` (PostgreSQL), `19000` (MinIO), and `19001` (MinIO Console), so app-level `.env` settings cannot remap them accidentally.

See `.env.example` for the full configuration surface, including tracing, storage, rate limiting, and market-data settings.

## Optional Capability Packs

Install only the packages you need:

```bash
pip install -e ".[embeddings]"
pip install -e ".[anthropic]"
pip install -e ".[celery]"
pip install -e ".[postgres]"
pip install -e ".[s3]"
pip install -e ".[market]"
pip install -e ".[monitoring]"
pip install -e ".[all]"
```

## Development

```bash
make test
make eval
python scripts/eval.py --thresholds benchmarks/thresholds/golden_minimum.json
make fmt
make lint
make typecheck
make web-lint
make web-build
```

The repository is organized around a small number of clear surfaces:

- `src/api/` for HTTP entry points and application wiring
- `src/pdf/` for extraction, rendering, tables, and OCR
- `src/finance/` for facts, normalization, validation, and signal logic
- `src/agent/` for pipeline orchestration and state handling
- `src/market/` for event-study analysis and market providers
- `web/` for the Vue 3 dashboard
- `tests/` for API, storage, pipeline, frontend-adjacent, and integration coverage
- `benchmarks/` for benchmark manifest schemas, threshold configs, and non-sensitive sample manifests
- `docs/` for architecture, branch protection, roadmap, and project notes

## Benchmark Data Policy

Benchmark manifests, anonymized labels, synthetic fixtures, schemas, and threshold configs can be committed. Raw third-party or proprietary PDFs, private labels, customer files, and generated benchmark artifacts must stay out of git.

Use `benchmarks/raw/` or `benchmarks/private/` for local-only datasets. Those paths are ignored by git. Store only stable metadata, expected facts, expected evidence pointers, and licensing notes in committed manifests.

## Contributing

All changes land through pull requests.

```bash
git checkout -b feat/<short-description>
bash scripts/local_ci.sh
git push -u origin HEAD
gh pr create --base main --fill
```

Before opening a PR, make sure local CI passes. The script covers Python linting, typing, tests, and the web checks that mirror CI.

See `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and `docs/BRANCH_PROTECTION.md` for project policy and contribution details.

## License

MIT. See `LICENSE`.

## Not Financial Advice

Jetbot produces structured extraction and analytical signals. It does not provide investment advice or recommend trades.
