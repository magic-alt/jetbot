# JetBot Financial Report Agent — Comprehensive Upgrade Plan

**Document Version**: 1.4
**Base Commit**: `0a338c0` (全量代码审查优化修复)
**Current State**: P1–P7 Complete — 319 tests passing, 10-node LangGraph pipeline, FastAPI + CLI, Mock/OpenAI/Anthropic LLM, Embedding RAG, Token Manager, Celery Task Queue, Postgres/S3 Storage, Market Data Event Study, Golden Test Suite, Prometheus Metrics, Docker, CI/CD

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Assessment](#2-current-state-assessment)
3. [Phase 1: Production Hardening](#3-phase-1-production-hardening)
4. [Phase 2: OCR & PDF Enhancement](#4-phase-2-ocr--pdf-enhancement)
5. [Phase 3: LLM & RAG Upgrade](#5-phase-3-llm--rag-upgrade)
6. [Phase 4: Async Task Queue & Storage Backend](#6-phase-4-async-task-queue--storage-backend)
7. [Phase 5: Market Data & Event Study](#7-phase-5-market-data--event-study)
8. [Phase 6: Evaluation & Quality Assurance](#8-phase-6-evaluation--quality-assurance)
9. [Phase 7: Observability & DevOps](#9-phase-7-observability--devops)
10. [File Change Matrix](#10-file-change-matrix)
11. [Dependency Changes](#11-dependency-changes)
12. [Risk Assessment](#12-risk-assessment)
13. [Acceptance Criteria Per Phase](#13-acceptance-criteria-per-phase)

---

## 1. Executive Summary

The JetBot Financial Report Agent MVP is functionally complete. All 9 LangGraph nodes, 7 API endpoints, 3 CLI commands, 12 Pydantic models, and 71 tests are operational. This plan defines a structured upgrade path from MVP to production-grade v1.0, organized into 7 independent phases that can be executed in parallel or sequentially.

**Key upgrade themes:**
- Production hardening (auth, rate limiting, input validation, error recovery)
- PDF capability expansion (OCR for scanned documents, improved table extraction)
- LLM pipeline maturity (embedding-based RAG, prompt optimization, token management)
- Infrastructure scaling (Celery/Redis task queue, Postgres/S3 storage, Docker)
- Market data integration (real-time stock data, event study with live feeds)
- Quality assurance (golden test set, regression testing, accuracy metrics)
- Observability (structured metrics, alerting, distributed tracing)

---

## 2. Current State Assessment

### 2.1 What's Working

| Component | Status | File(s) | Lines |
|-----------|--------|---------|-------|
| Pydantic v2 schemas (12 models) | Complete | `src/schemas/models.py` | 167 |
| LangGraph 9-node pipeline | Complete + Optimized | `src/agent/graph.py`, `nodes.py` | 1047 |
| PDF text extraction (PyMuPDF) | Complete | `src/pdf/extractor.py` | 51 |
| Table extraction (pdfplumber) | Complete | `src/pdf/tables.py` | 62 |
| Financial validators (balance eq, unit, line items) | Complete | `src/finance/validators.py` | 89 |
| Risk signal generation (4 types) | Complete | `src/finance/signals.py` | 142 |
| Account normalization (CN+EN) | Complete | `src/finance/normalizer.py` | 21 |
| LLM abstraction (Protocol + Mock + OpenAI) | Complete | `src/llm/*.py` | ~400 |
| FastAPI (7 endpoints) | Complete | `src/api/routes.py` | 148 |
| CLI (3 commands) | Complete | `src/cli.py` | ~100 |
| Local storage + SQLite task store | Complete | `src/storage/*.py` | ~290 |
| Token-overlap RAG | Complete | `src/storage/vector_index.py` | 130 |
| Market data (Dummy + YFinance stubs) | Complete | `src/market/*.py` | ~110 |
| Tests (71 passing) | Complete | `tests/*.py` | ~600 |

### 2.2 Known Gaps

| Gap | Severity | Current State | Target |
|-----|----------|--------------|--------|
| OCR for scanned PDFs | High | Stub (`run_ocr` returns `""`) | PaddleOCR + Tesseract |
| Page rendering | Low | Stub (`render_pages` returns `[]`) | Integrated into extractor |
| LLM token limit management | Medium | No enforcement | Chunked prompts with overflow protection |
| Embedding-based RAG | Medium | Token overlap only | FAISS/HNSWlib with sentence embeddings |
| API authentication | High | None | API key / JWT |
| Rate limiting | Medium | None | Per-client throttling |
| Task queue | Medium | FastAPI BackgroundTasks | Celery + Redis |
| Database | Low (MVP) | SQLite + local JSON | Postgres + S3 |
| CI/CD pipeline | Medium | None | GitHub Actions |
| Docker deployment | Medium | None | Dockerfile + docker-compose |
| Golden test set | Medium | 1 mock E2E test | 5+ real PDF fixtures with expected outputs |
| Input sanitization | High | Path traversal protected | Full multipart/PDF validation |

---

## 3. Phase 1: Production Hardening

**Goal**: Make the API safe for deployment behind a reverse proxy.

### 3.1 API Authentication

Add API key authentication middleware with `API_KEYS` env var (comma-separated), 401 on invalid/missing key, skip auth for health check, `GET /health` endpoint.

### 3.2 Rate Limiting

Per-IP rate limits: 60 req/min read, 10 req/min analyze, 5 req/min upload. Configurable via `RATE_LIMIT_*` env vars.

### 3.3 Input Validation & Security

Validate MIME type, enforce max file size, validate `%PDF-` header bytes, sanitize filename, add Content-Security-Policy headers.

### 3.4 Graceful Error Recovery

Per-node timeout (default 120s), circuit breaker for LLM calls, persist partial results on failure, `on_error` callback to update task status.

### 3.5 Tests for Phase 1

- `tests/test_auth.py`: API key validation
- `tests/test_input_validation.py`: File size, MIME, PDF header, filename sanitization

---

## 4. Phase 2: OCR & PDF Enhancement

**Goal**: Handle scanned PDFs and improve table extraction accuracy.

### 4.1 OCR Integration

PaddleOCR (primary, best for Chinese) + Tesseract (fallback for English). Auto-detect language. Cache OCR results per page.

### 4.2 Page Rendering Enhancement

Use PyMuPDF (fitz) for page-to-image rendering at configurable DPI (default 200 for OCR, 72 for preview). Save as PNG with consistent naming.

### 4.3 Table Extraction Improvements

Add camelot-py as secondary extractor, table merging across pages, header detection, confidence scoring.

### 4.4 Tests for Phase 2

- `tests/test_ocr.py`: OCR engine factory, language detection
- `tests/test_render.py`: Page rendering with DPI, selective rendering

---

## 5. Phase 3: LLM & RAG Upgrade

**Goal**: Better retrieval, token management, and multi-model support.

### 5.1 Embedding-Based RAG

Replace token-overlap with FAISS + sentence-transformers. Hybrid scoring: 0.7 × embedding + 0.3 × BM25. Configurable via `RAG_MODE` env var.

### 5.2 Token Limit Management

Count tokens (tiktoken for OpenAI, estimate for others), truncate context on overflow, configurable via `MODEL_MAX_TOKENS`.

### 5.3 Multi-Model Support

Task routing: `LLM_EXTRACTION_MODEL`, `LLM_REPORT_MODEL`, `LLM_DEFAULT_MODEL`. Anthropic Claude client added.

### 5.4 Prompt Template Optimization

Add few-shot examples (1-2 per prompt), anti-hallucination rules, unit/currency normalization instructions.

### 5.5 Tests for Phase 3

- `tests/test_token_manager.py`: Token counting, truncation, splitting
- `tests/test_embedding_index.py`: Embedding index CRUD, search, hybrid retrieval

---

## 6. Phase 4: Async Task Queue & Storage Backend

**Goal**: Replace in-process background tasks with a scalable task queue and persistent storage.

### 6.1 Celery + Redis Task Queue

Celery worker with Redis broker. Task: `run_analysis`. Progress reporting per node. Retry policy: 2 retries with exponential backoff. `TASK_BACKEND=background|celery`.

### 6.2 Postgres Storage Backend

SQLAlchemy ORM with Postgres. `StorageBackend` Protocol abstraction. `STORAGE_BACKEND=local|postgres`. Dual-write strategy.

### 6.3 S3/MinIO Object Storage

S3-compatible client (boto3). Local file storage fallback. `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.

### 6.4 Tests for Phase 4

- `tests/test_celery_task.py`: Task dispatch, backend switching
- `tests/test_pg_store.py`: CRUD, Protocol satisfaction, factory
- `tests/test_object_store.py`: S3 mock + local path tests

---

## 7. Phase 5: Market Data & Event Study

**Goal**: Enable real stock price analysis and event study with live data.

### 7.1 Market Data Provider Upgrade

Add Tushare provider (A-share) and Polygon.io provider (US). Auto-detect market from ticker format. Local cache with TTL.

### 7.2 Event Study Enhancement

Market-adjusted abnormal return (CAPM), statistical significance test (t-test), multiple event windows, event study chart.

### 7.3 Integration into Pipeline

Optional `run_event_study_node` between `build_trader_report` and `finalize`. Conditional edge if market data available.

### 7.4 Tests for Phase 5

- `tests/test_market_providers.py`: Mock Tushare/Polygon responses
- `tests/test_event_study_extended.py`: Abnormal return calculation

---

## 8. Phase 6: Evaluation & Quality Assurance

**Goal**: Systematic accuracy measurement and regression prevention.

### 8.1 Golden Test Set

5-10 representative PDFs (or synthetic equivalents). For each: expected outputs (statements, notes, signals). Field-level comparison with configurable tolerance.

### 8.2 Accuracy Metrics Dashboard

Track: extraction accuracy, balance equation pass rate, signal precision/recall, source reference completeness, pipeline completion rate.

### 8.3 Regression Testing

Snapshot comparison on each golden run. Alert on accuracy drops. CI integration.

### 8.4 Tests for Phase 6

- `tests/golden/test_golden.py`: Parametrized golden test cases
- `tests/test_metrics.py`: Metric computation unit tests

---

## 9. Phase 7: Observability & DevOps

**Goal**: Production monitoring, containerization, and CI/CD.

### 9.1 Structured Metrics & Monitoring

Prometheus `/metrics` endpoint. Key metrics: pipeline duration, LLM call duration/tokens, active analyses, PDF pages.

### 9.2 Distributed Tracing

OpenTelemetry with Jaeger/OTLP exporter. Trace spans from API request through LangGraph nodes to LLM calls.

### 9.3 Docker & Docker Compose

Multi-stage Dockerfile (builder + slim runtime). docker-compose: api + worker + redis + postgres + minio.

### 9.4 CI/CD Pipeline

GitHub Actions: lint → type check → unit tests → golden tests → Docker build → push on tag.

### 9.5 Tests for Phase 7

- `tests/test_metrics_collector.py`: Metric recording
- `tests/test_docker.py`: Build and start validation

---

## 10. File Change Matrix

### New Files

| File | Phase | Description |
|------|-------|-------------|
| `src/api/auth.py` | P1 | API key authentication |
| `src/llm/token_manager.py` | P3 | Token counting and truncation |
| `src/llm/anthropic_client.py` | P3 | Anthropic Claude client |
| `src/tasks/__init__.py` | P4 | Celery app configuration |
| `src/tasks/analysis.py` | P4 | Celery analysis task |
| `src/storage/pg_store.py` | P4 | Postgres storage backend |
| `src/storage/backend.py` | P4 | Storage Protocol abstraction |
| `src/storage/object_store.py` | P4 | S3/MinIO object storage |
| `src/market/cache.py` | P5 | Market data local cache |
| `src/utils/metrics.py` | P6 | Accuracy metrics computation |
| `src/utils/metrics_collector.py` | P7 | Prometheus instrumentation |
| `src/utils/tracing.py` | P7 | OpenTelemetry setup |
| `scripts/eval.py` | P6 | Evaluation CLI script |
| `tests/golden/` | P6 | Golden test infrastructure |
| `tests/test_auth.py` | P1 | Auth tests |
| `tests/test_input_validation.py` | P1 | Input validation tests |
| `tests/test_ocr.py` | P2 | OCR tests |
| `tests/test_render.py` | P2 | Rendering tests |
| `tests/test_token_manager.py` | P3 | Token manager tests |
| `tests/test_embedding_index.py` | P3 | Embedding index tests |
| `tests/test_celery_task.py` | P4 | Celery task tests |
| `tests/test_pg_store.py` | P4 | Postgres storage tests |
| `Dockerfile` | P7 | Container build |
| `docker-compose.yml` | P7 | Multi-service composition |
| `.github/workflows/ci.yml` | P7 | CI pipeline |
| `alembic/` | P4 | Database migrations |

### Modified Files

| File | Phases | Key Changes |
|------|--------|-------------|
| `src/api/main.py` | P1,P7 | Auth, rate limit, metrics, health endpoint |
| `src/api/routes.py` | P1,P4 | Auth decorator, Celery dispatch, input validation |
| `src/agent/nodes.py` | P1,P2,P3,P5 | Timeouts, OCR integration, token mgmt, event study node |
| `src/agent/graph.py` | P1,P5 | Error callback, event study edge |
| `src/pdf/ocr.py` | P2 | Full OCR implementation |
| `src/pdf/render.py` | P2 | Full rendering implementation |
| `src/pdf/tables.py` | P2 | Camelot integration, header detection |
| `src/pdf/extractor.py` | P1,P2 | PDF header validation, OCR pass |
| `src/llm/base.py` | P1,P3 | Timeout param, task routing |
| `src/llm/openai_client.py` | P3,P7 | Token checking, metrics recording |
| `src/storage/vector_index.py` | P3 | Embedding-based index |
| `src/storage/task_store.py` | P4 | Progress percentage tracking |
| `src/market/provider.py` | P5 | Tushare, Polygon providers |
| `src/market/event_study.py` | P5 | Abnormal returns, significance tests |
| `src/schemas/models.py` | P5 | EventStudyResult in TraderReport |
| `src/prompts/*.md` | P3 | Few-shot examples, improved instructions |
| `pyproject.toml` | ALL | New dependencies per phase |
| `.env.example` | ALL | New config vars per phase |
| `Makefile` | P4,P6,P7 | worker, eval, docker targets |
| `tests/test_pipeline_mock.py` | P2,P3,P5 | OCR path, embedding RAG, event study |

---

## 11. Dependency Changes

### Phase 1
```toml
slowapi = ">=0.1"
```

### Phase 2
```toml
[project.optional-dependencies]
ocr = ["paddleocr>=2.7", "paddlepaddle>=2.5", "pytesseract>=0.3"]
tables = ["camelot-py[cv]>=0.11"]
```

### Phase 3
```toml
[project.optional-dependencies]
embeddings = ["faiss-cpu>=1.7", "sentence-transformers>=2.2"]
anthropic = ["anthropic>=0.40"]
# core
tiktoken = ">=0.7"
```

### Phase 4
```toml
[project.optional-dependencies]
celery = ["celery[redis]>=5.3"]
postgres = ["sqlalchemy[asyncio]>=2.0", "asyncpg>=0.29", "alembic>=1.13"]
s3 = ["boto3>=1.34"]
```

### Phase 5
```toml
[project.optional-dependencies]
market = ["tushare>=1.4", "polygon-api-client>=1.12", "matplotlib>=3.8"]
```

### Phase 7
```toml
[project.optional-dependencies]
monitoring = ["prometheus-client>=0.20", "opentelemetry-api>=1.22", "opentelemetry-sdk>=1.22"]
dev = ["pytest>=7.4", "pytest-asyncio>=0.23", "ruff>=0.5", "mypy>=1.8", "moto[s3]>=5.0"]
```

### Convenience Extras
```toml
[project.optional-dependencies]
all = ["jetbot[ocr,tables,embeddings,celery,postgres,s3,market,monitoring]"]
```

---

## 12. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PaddleOCR install complexity | High | Medium | Docker image with pre-built OCR; fallback to Tesseract |
| FAISS/sentence-transformers GPU memory | Medium | Medium | CPU-only FAISS; lazy model loading |
| Celery adds operational complexity | Medium | Low | Keep BackgroundTasks as default; Celery opt-in |
| Postgres migration breaks local dev | Low | High | Keep SQLite as default; Postgres opt-in |
| Token limit changes break existing prompts | Medium | Medium | Test all prompts with token manager before deploy |
| Market data API rate limits | High | Low | Local caching with TTL; graceful degradation |
| Docker image size bloat (OCR deps) | High | Low | Multi-stage build; separate OCR image variant |
| LangGraph version incompatibility | Low | High | Pin LangGraph version; test against minor releases |

---

## 13. Acceptance Criteria Per Phase

### Phase 1: Production Hardening ✅
- [x] API returns 401 for missing/invalid API key
- [x] API returns 429 when rate limit exceeded
- [x] Uploading non-PDF file returns 400 with clear error message
- [x] Uploading file > MAX_UPLOAD_SIZE_MB returns 413
- [x] Pipeline timeout triggers graceful failure with partial results saved
- [x] `/health` endpoint returns 200 with version info
- [x] All existing 71 tests still pass
- [x] New auth/validation tests pass (target: 80+ total tests)

### Phase 2: OCR & PDF Enhancement ✅
- [x] Scanned PDF (image-only) produces text output via OCR
- [x] OCR language auto-detection works for Chinese and English
- [x] Page rendering produces PNG files at configurable DPI
- [x] Borderless tables are extracted (camelot or improved pdfplumber)
- [x] Multi-page tables are merged correctly
- [x] Pipeline works end-to-end on scanned PDF fixture
- [x] All tests pass (target: 90+ total tests)

### Phase 3: LLM & RAG Upgrade ✅
- [x] Embedding-based search returns more relevant chunks than token-overlap
- [x] Token manager prevents context overflow (tested with 100+ page PDF)
- [x] Anthropic Claude client works as drop-in replacement for OpenAI
- [x] Model routing correctly dispatches extraction vs report tasks
- [x] Few-shot prompts produce higher quality extraction (measured on golden set)
- [x] All tests pass (target: 100+ total tests)

### Phase 4: Async Task Queue & Storage Backend ✅
- [x] `TASK_BACKEND=celery`: tasks dispatched to Celery worker
- [x] Task progress updates at each pipeline node
- [x] Failed Celery tasks retry up to 2 times
- [x] `STORAGE_BACKEND=postgres`: all CRUD operations work against Postgres
- [x] Alembic migration applies cleanly on fresh database
- [x] `STORAGE_BACKEND=local` still works (no regression)
- [x] All tests pass (target: 110+ total tests) — **162 tests passing**

### Phase 5: Market Data & Event Study ✅
- [x] Tushare provider returns A-share prices when configured
- [x] Event study calculates market-adjusted abnormal returns
- [x] Statistical significance test produces p-values
- [x] Event study chart saved as PNG in report directory
- [x] Pipeline includes event study when market data is available
- [x] Pipeline completes without error when market data is unavailable
- [x] All tests pass (target: 120+ total tests)

### Phase 6: Evaluation & Quality Assurance ✅
- [x] Golden test set has 5+ representative cases
- [x] `make eval` runs all golden tests and reports accuracy metrics
- [x] Regression detection catches accuracy drops
- [x] Source reference completeness > 95% on golden set
- [x] Balance equation pass rate > 90% on golden set
- [x] All tests pass (target: 130+ total tests)

### Phase 7: Observability & DevOps ✅
- [x] `/metrics` endpoint returns Prometheus-formatted metrics
- [x] Docker image builds and runs successfully
- [x] `docker-compose up` starts full stack (API + worker + Redis + Postgres)
- [x] CI pipeline runs lint + tests on every push
- [x] Release pipeline builds and tags Docker image
- [x] All tests pass (target: 140+ total tests) — **319 tests passing**

---

## Appendix A: Environment Variable Reference (Complete)

```bash
# === LLM Configuration ===
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
ANTHROPIC_API_KEY=
LLM_DEFAULT_MODEL=
LLM_EXTRACTION_MODEL=
LLM_REPORT_MODEL=
LLM_TIMEOUT_S=60
MODEL_MAX_TOKENS=128000

# === LangSmith Tracing ===
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=financial-report-agent

# === Storage ===
DATA_DIR=data
STORAGE_BACKEND=local
DATABASE_URL=
S3_ENDPOINT=
S3_BUCKET=jetbot-pdfs
S3_ACCESS_KEY=
S3_SECRET_KEY=

# === Task Queue ===
TASK_BACKEND=background
CELERY_BROKER_URL=redis://localhost:6379/0

# === API Security ===
API_KEYS=
CORS_ORIGINS=*
RATE_LIMIT_READ=60
RATE_LIMIT_ANALYZE=10
RATE_LIMIT_UPLOAD=5
MAX_UPLOAD_SIZE_MB=100
NODE_TIMEOUT_S=120

# === RAG ===
RAG_MODE=token_overlap
EMBEDDING_MODEL=auto

# === Market Data ===
MARKET_DATA_PROVIDER=dummy
TUSHARE_TOKEN=
POLYGON_API_KEY=

# === Observability ===
DEBUG=0
OTLP_ENDPOINT=
```

---

## Appendix B: Makefile Targets (Complete)

```makefile
.PHONY: dev test fmt lint typecheck worker eval docker-build docker-up docker-down

dev:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest

fmt:
	python -m ruff format src tests

lint:
	python -m ruff check src tests

typecheck:
	python -m mypy src --ignore-missing-imports

worker:
	celery -A src.tasks worker --loglevel=info --concurrency=2

eval:
	python -m pytest tests/golden/ -v --tb=short

docker-build:
	docker build -t jetbot:latest .

docker-up:
	docker compose up -d

docker-down:
	docker compose down
```

---

*End of Upgrade Plan*
