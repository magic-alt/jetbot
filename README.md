# Financial Report PDF Agent

A FastAPI service and CLI for parsing financial report PDFs, extracting structured statements and notes, running validation checks, and generating a trader-style report with evidence references.

Supports mock mode (no API key required), OpenAI, and Anthropic Claude models. Includes OCR for scanned PDFs, embedding-based RAG retrieval, token overflow protection, and optional Celery/Postgres/S3 infrastructure.

## Quick Start (Mock Mode)

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .
make dev
```

Upload a PDF and trigger analysis (mock LLM if `OPENAI_API_KEY` is not set).

## Configure LLM

### OpenAI

1. Copy `.env.example` to `.env`
2. Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` (default: `gpt-4.1-mini`)
3. Restart the API or CLI

### Anthropic Claude

1. Set `ANTHROPIC_API_KEY` in `.env`
2. Set `LLM_DEFAULT_MODEL=anthropic:claude-sonnet-4-20250514` (or other Claude model)

### Multi-Model Routing

Route different tasks to different models for cost/quality optimization:

```bash
LLM_EXTRACTION_MODEL=openai:gpt-4.1       # High-accuracy for statement extraction
LLM_REPORT_MODEL=openai:gpt-4.1-mini      # Fast model for report generation
```

Format: `provider:model` (e.g. `openai:gpt-4.1`, `anthropic:claude-sonnet-4-20250514`)

### LangSmith Tracing (Optional)

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-key>
LANGSMITH_PROJECT=financial-report-agent
```

## RAG Retrieval Modes

Set `RAG_MODE` in `.env`:

| Mode | Description | Dependencies |
|------|-------------|-------------|
| `token_overlap` (default) | Lightweight token-overlap scoring | None |
| `embedding` | FAISS + sentence-transformers | `pip install -e ".[embeddings]"` |
| `hybrid` | 0.7 embedding + 0.3 BM25 fusion | `pip install -e ".[embeddings]"` |

Embedding model is auto-selected by document language (Chinese: `bge-base-zh`, English: `all-MiniLM`). Override with `EMBEDDING_MODEL`.

## Infrastructure Options

### Celery Task Queue (Optional)

```bash
TASK_BACKEND=celery
CELERY_BROKER_URL=redis://localhost:6379/0
```

Start worker: `make worker`

### PostgreSQL Storage (Optional)

```bash
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://user:pass@localhost/jetbot
```

Install: `pip install -e ".[postgres]"`

### S3/MinIO Object Storage (Optional)

```bash
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=jetbot-pdfs
S3_ACCESS_KEY=minio
S3_SECRET_KEY=minio123
```

Install: `pip install -e ".[s3]"`

## API Examples

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# Upload PDF
curl -F "file=@path/to/report.pdf" \
     -H "X-API-Key: your-key" \
     http://localhost:8000/v1/documents

# Trigger analysis
curl -X POST -H "X-API-Key: your-key" \
     http://localhost:8000/v1/documents/<doc_id>/analyze

# Get task status
curl -H "X-API-Key: your-key" \
     http://localhost:8000/v1/documents/<doc_id>

# Get markdown report
curl -H "X-API-Key: your-key" \
     http://localhost:8000/v1/documents/<doc_id>/report.md

# Get structured statements
curl -H "X-API-Key: your-key" \
     http://localhost:8000/v1/documents/<doc_id>/statements

# Get risk signals
curl -H "X-API-Key: your-key" \
     http://localhost:8000/v1/documents/<doc_id>/risk-signals
```

Note: `API_KEYS` env var controls authentication. Leave blank to disable auth.

## CLI Examples

```bash
python -m src.cli analyze --pdf path/to/report.pdf --out data --company "Example Co" --period-end 2025-12-31
python -m src.cli show --doc-id <doc_id> --what report
python -m src.cli render-report --doc-id <doc_id>
```

## Output Files

Results are stored under `data/{doc_id}/`:

- `raw.pdf` — uploaded PDF
- `meta.json` — document metadata
- `extracted/pages.json` — per-page text
- `extracted/tables.json` — extracted tables
- `extracted/statements.json` — structured financial statements
- `extracted/notes.json` — key notes (accounting policy, audit opinion, etc.)
- `extracted/risk_signals.json` — risk signals with evidence
- `report/trader_report.json` — structured trader report
- `report/trader_report.md` — markdown trader report

## Development

```bash
make test        # Run 162 tests
make fmt         # Format code (ruff)
make lint        # Lint code (ruff)
make typecheck   # Type check (mypy)
```

### Optional Dependencies

```bash
pip install -e ".[embeddings]"   # FAISS + sentence-transformers
pip install -e ".[anthropic]"    # Anthropic Claude
pip install -e ".[celery]"       # Celery + Redis
pip install -e ".[postgres]"     # PostgreSQL + SQLAlchemy
pip install -e ".[s3]"           # S3/MinIO (boto3)
pip install -e ".[all]"          # Everything
```

## Not Financial Advice

This system provides structured extraction and analytical signals only. It does not provide investment advice or recommend trades.
