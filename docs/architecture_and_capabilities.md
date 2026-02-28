# 财报 PDF Agent 架构与能力说明

## 1. 文档目的

本文档用于说明当前仓库的：

- 软件架构（分层、模块职责、工作流）
- 技术栈与关键依赖
- 当前版本已经达到的效果（可运行能力）
- 已知限制与后续扩展方向

说明基于当前代码实现（`src/` + `tests/`），涵盖 MVP 及 P1–P4 阶段升级。

## 2. 系统定位

该项目是一个"财报 PDF 智能解析与交易员分析 Agent"系统，提供两种入口：

- FastAPI 服务：上传 PDF、触发分析、查询结构化结果与报告
- CLI：离线执行单份 PDF 分析并输出结果文件

系统核心目标是：

1. 从财报 PDF 抽取文本与表格（支持扫描件 OCR）
2. 结构化三大表（利润表/资产负债表/现金流量表）
3. 生成关键注释与风险信号
4. 输出带证据引用的 Trader 风格报告

## 3. 总体架构

### 3.1 分层结构

当前代码对应如下分层：

**1. 接入层（API/CLI）**
- `src/api/main.py` — FastAPI 入口，CORS、安全头、`/health` 端点
- `src/api/auth.py` — [P1] API Key 认证依赖（读取 `API_KEYS` 环境变量）
- `src/api/routes.py` — `/v1/documents` 全部端点，含速率限制、输入校验、Celery 分发
- `src/cli.py` — Typer CLI（analyze / render-report / show）

**2. 编排层（LangGraph）**
- `src/agent/graph.py` — 有状态工作流，含条件分支与重试
- `src/agent/nodes.py` — 9 节点函数（含节点超时、token 截断、RAG 上下文组装）
- `src/agent/state.py` — `AgentState` 定义

**3. PDF 处理层**
- `src/pdf/extractor.py` — PyMuPDF 文本抽取 + PDF 格式校验（`%PDF-` 头部检测）
- `src/pdf/tables.py` — pdfplumber 表格抽取
- `src/pdf/ocr.py` — [P2] PaddleOCR + Tesseract 双引擎 OCR，Protocol 抽象，自动语言检测
- `src/pdf/render.py` — [P2] PyMuPDF 页面渲染，可配 DPI（默认 200 OCR / 72 预览）

**4. 财务语义与规则层**
- `src/finance/normalizer.py` — 科目归一（中英文）
- `src/finance/validators.py` — 勾稽校验（资产负债平衡、单位一致性、字段完整性）
- `src/finance/signals.py` — 风险信号生成（现金流背离、应收/存货异常、审计意见、披露不一致）

**5. LLM 抽象层**
- `src/llm/base.py` — [P3] `LLMClient` Protocol + 多模型路由 `get_llm_client(task)`，支持按任务（extraction / report / validation）分发到不同模型
- `src/llm/mock.py` — MockLLMClient，无 Key 可运行
- `src/llm/openai_client.py` — OpenAI 客户端（`langchain_openai.ChatOpenAI` + 结构化输出 + token 截断）
- `src/llm/anthropic_client.py` — [P3] Anthropic Claude 客户端（drop-in 替换）
- `src/llm/token_manager.py` — [P3] Token 计数（tiktoken / 启发式）、截断、分块、上下文溢出保护

**6. 存储与任务状态层**
- `src/storage/local_store.py` — 本地文件持久化（满足 `StorageBackend` Protocol）
- `src/storage/task_store.py` — [P4] SQLite 任务状态，含 `current_node` 字段和节点级进度追踪（15%–100%）
- `src/storage/vector_index.py` — [P3] 三种 RAG 模式：Token-overlap（`LocalVectorIndex`）、Embedding（`EmbeddingVectorIndex`，FAISS + sentence-transformers）、Hybrid（`HybridRetriever`，α=0.7 embedding + 0.3 BM25）
- `src/storage/backend.py` — [P4] `StorageBackend` Protocol 抽象 + `get_storage_backend()` 工厂
- `src/storage/pg_store.py` — [P4] PostgreSQL 存储后端（SQLAlchemy ORM，双写 PG + 本地）
- `src/storage/object_store.py` — [P4] S3/MinIO 对象存储（boto3，本地文件系统 fallback）

**7. 异步任务层**
- `src/tasks/__init__.py` — [P4] Celery 应用配置（Redis broker，可选启用）
- `src/tasks/analysis.py` — [P4] `run_analysis` 任务（bind=True, max_retries=2, 指数退避）

**8. 公共工具层**
- `src/utils/logging.py` — 结构化日志（`ContextLoggerAdapter`）
- `src/utils/ids.py` — ID 生成
- `src/utils/time.py` — 时间工具

### 3.2 工作流（LangGraph）

状态模型：`AgentState`（`src/agent/state.py`），核心字段包括：

- `pages/chunks/tables/statements/notes/risk_signals/trader_report`
- `validation_results/errors/debug`
- `retry_count/needs_ocr`

执行链路（`src/agent/graph.py`）：

1. `ingest_pdf` — PDF 文本抽取，扫描件检测，OCR（如需要），页面渲染
2. `extract_tables` — pdfplumber 表格抽取
3. `detect_sections_and_chunk` — 章节识别与 chunk 切分
4. `extract_financial_statements` — 三大表定位与 LLM 结构化映射
5. `validate_and_reconcile` — 勾稽/一致性校验
6. 条件分支：
   - 若出现严重校验问题且重试次数 `< 2`，回到 `extract_financial_statements`
   - 否则继续
7. `extract_key_notes` — LLM 抽取关键注释
8. `generate_risk_signals` — 规则 + LLM 生成风险信号
9. `build_trader_report` — Trader 风格报告生成（RAG 上下文组装）
10. `finalize` — 持久化全部结果

节点超时：每个节点受 `NODE_TIMEOUT_S` 控制（默认 120s），LLM 调用受 `LLM_TIMEOUT_S` 控制（默认 60s）。

### 3.3 RAG 检索子系统

`src/storage/vector_index.py` 提供三种检索模式（由 `RAG_MODE` 环境变量切换）：

| 模式 | 实现 | 依赖 |
|------|------|------|
| `token_overlap`（默认） | `LocalVectorIndex` — 基于 token 重叠的轻量检索 | 无额外依赖 |
| `embedding` | `EmbeddingVectorIndex` — FAISS flat L2 + sentence-transformers | `faiss-cpu`, `sentence-transformers` |
| `hybrid` | `HybridRetriever` — 0.7 × embedding + 0.3 × BM25 倒数排名融合 | 同上 |

Embedding 模型自动选择：中文文档 → `BAAI/bge-base-zh-v1.5`，英文文档 → `all-MiniLM-L6-v2`。可通过 `EMBEDDING_MODEL` 环境变量覆盖。

当 FAISS/sentence-transformers 不可用时，`embedding` 和 `hybrid` 模式自动降级到 `token_overlap`。

### 3.4 多模型路由

`src/llm/base.py` 中的 `get_llm_client(task)` 支持按任务类型分发：

| 任务 | 环境变量 | 默认值 |
|------|---------|--------|
| extraction | `LLM_EXTRACTION_MODEL` | 回退到 `LLM_DEFAULT_MODEL` |
| report | `LLM_REPORT_MODEL` | 回退到 `LLM_DEFAULT_MODEL` |
| validation | `LLM_VALIDATION_MODEL` | 回退到 `LLM_DEFAULT_MODEL` |
| 其他 | `LLM_DEFAULT_MODEL` | 回退到 `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → Mock |

模型规格格式：`provider:model`（如 `openai:gpt-4.1`、`anthropic:claude-sonnet-4-20250514`），或仅模型名（自动推断 provider）。

## 4. 技术栈

来自 `pyproject.toml` 的当前技术栈：

**核心依赖**
- Python `>=3.12`
- Web/API：`FastAPI` + `Uvicorn` + `slowapi`（速率限制）
- 编排：`LangGraph`
- Schema：`Pydantic v2`
- CLI：`Typer`
- PDF：`PyMuPDF`, `pdfplumber`
- 数据计算：`pandas`
- LLM：`openai` SDK + `langchain` + `langchain-openai`
- Token 管理：`tiktoken`
- 日志：`logging`（自定义 `ContextLoggerAdapter`）

**可选依赖**
- OCR：`paddleocr`, `pytesseract`
- Embedding RAG：`faiss-cpu`, `sentence-transformers`
- Anthropic：`anthropic`
- 任务队列：`celery[redis]`
- 数据库：`sqlalchemy`, `asyncpg`, `alembic`
- 对象存储：`boto3`

**开发 & 测试**
- `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `moto[s3]`

运行入口：

| 命令 | 用途 |
|------|------|
| `make dev` | 启动 FastAPI 开发服务（uvicorn --reload） |
| `make test` | 运行全部 162 测试 |
| `make fmt` | ruff format |
| `make lint` | ruff check |
| `make typecheck` | mypy 类型检查 |
| `make worker` | 启动 Celery worker（需 Redis） |
| `python -m src.cli analyze --pdf <file>` | CLI 分析 |

## 5. 数据模型与可追溯性设计

统一模型在 `src/schemas/models.py`，重点包括：

- 文档结构：`DocumentMeta`, `Page`, `Chunk`
- 表格结构：`Table`, `TableCell`
- 财务结构：`FinancialStatement`, `StatementLineItem`
- 语义输出：`KeyNote`, `RiskSignal`, `TraderReport`
- 证据对象：`SourceRef`

可追溯性实现要点：

1. 关键实体（line item、notes、signals）都包含 `SourceRef`
2. `SourceRef` 记录 `ref_type/page/table_id/quote/confidence`
3. 当上游抽取证据不足时，节点会填充 fallback evidence，避免出现"完全无引用"的结果

## 6. API 与 CLI 能力

### 6.1 API（`/v1`）

已实现接口：

| 方法 | 路径 | 说明 | 认证 | 速率限制 |
|------|------|------|------|---------|
| GET | `/health` | 健康检查 + 版本 | 否 | — |
| POST | `/v1/documents` | 上传 PDF | 是 | 5/min |
| POST | `/v1/documents/{doc_id}/analyze` | 触发分析 | 是 | 10/min |
| GET | `/v1/documents/{doc_id}` | 文档元信息 + 任务状态 | 是 | 60/min |
| GET | `/v1/documents/{doc_id}/report` | TraderReport JSON | 是 | 60/min |
| GET | `/v1/documents/{doc_id}/report.md` | Markdown 报告 | 是 | 60/min |
| GET | `/v1/documents/{doc_id}/statements` | 三大表 JSON | 是 | 60/min |
| GET | `/v1/documents/{doc_id}/notes` | 关键注释 | 是 | 60/min |
| GET | `/v1/documents/{doc_id}/risk-signals` | 风险信号 | 是 | 60/min |

安全特性：
- **API Key 认证**：通过 `X-API-Key` 请求头验证（`API_KEYS` 环境变量配置，留空则关闭认证）
- **速率限制**：基于 slowapi 的 per-IP 限流（`RATE_LIMIT_*` 环境变量配置）
- **输入校验**：PDF MIME 类型、`%PDF-` 头部字节、文件大小（`MAX_UPLOAD_SIZE_MB`）、文件名清理
- **安全头**：Content-Security-Policy 等标准安全响应头

返回结构采用统一 envelope：

- 成功：`{"ok": true, "data": ..., "error": null}`
- 失败：`{"ok": false, "data": null, "error": {"code": "...", "message": "..."}}`

### 6.2 CLI

已实现命令（`python -m src.cli --help`）：

- `analyze` — 分析 PDF 并输出结果
- `render-report` — 渲染已有分析报告
- `show` — 查看指定文档的报告/信号/报表

### 6.3 任务分发

分析任务支持两种分发模式（由 `TASK_BACKEND` 环境变量控制）：

| 模式 | 说明 |
|------|------|
| `background`（默认） | FastAPI `BackgroundTasks`，进程内执行 |
| `celery` | Celery worker 通过 Redis 分发，支持 max_retries=2 指数退避 |

任务进度追踪：`TaskStore`（SQLite）记录每个文档的 `status`、`progress`（0–100%）、`current_node`，每个 LangGraph 节点完成时自动更新。

## 7. 存储架构

### 7.1 本地存储布局

默认在 `data/`，单文档目录结构：

```
data/{doc_id}/
  raw.pdf
  meta.json
  extracted/
    pages.json
    tables.json
    statements.json
    notes.json
    risk_signals.json
  report/
    trader_report.json
    trader_report.md
```

任务状态：`data/tasks.db`（SQLite）

### 7.2 存储后端（P4）

`StorageBackend` Protocol 提供统一抽象，由 `get_storage_backend()` 根据 `STORAGE_BACKEND` 环境变量选择：

| 后端 | 实现 | 说明 |
|------|------|------|
| `local`（默认） | `LocalStore` | 本地文件系统 |
| `postgres` | `PgStore` | SQLAlchemy ORM，双写到 PG + 本地文件 |

### 7.3 对象存储（P4）

`ObjectStore` 类提供 S3 兼容的对象存储（PDF 和页面图片）：

- 配置 `S3_ENDPOINT` + `S3_ACCESS_KEY` + `S3_SECRET_KEY` → 使用 S3/MinIO
- 未配置 → 回退到本地文件系统
- API：`put(key, data)`, `get(key)`, `delete(key)`, `exists(key)`

## 8. 当前已达到的效果

### 8.1 可运行性

1. API 服务可启动并提供完整接口链路（含认证、限流、输入校验）
2. CLI 可执行分析命令并产出报告文件
3. 未配置 `OPENAI_API_KEY` 时可走 `MockLLM` 跑通全链路
4. 配置 OpenAI Key 后可切换到真实模型客户端
5. 配置 `ANTHROPIC_API_KEY` 后可使用 Claude 模型
6. 支持按任务类型路由到不同 LLM 模型

### 8.2 处理能力

1. PDF 页级文本抽取与页面渲染（可配 DPI）
2. 扫描件自动检测与 OCR 处理（PaddleOCR 中文 / Tesseract 英文）
3. 表格候选抽取并转结构化 `Table`
4. 三大表抽取：规则识别 + LLM 兜底
5. 勾稽与一致性校验（资产负债平衡、单位一致性、关键字段完整性等）
6. 规则化风险信号生成（现金流背离、披露不一致、审计意见等）
7. Token 溢出保护：LLM 调用前自动检测并截断上下文
8. 三种 RAG 检索模式：token-overlap / embedding / hybrid
9. 节点内使用 `ChatPromptTemplate + with_structured_output`
10. 在关键节点使用 `RunnableParallel` 并行 LLM 分支
11. Few-shot 提示词优化（含中文财报示例和反幻觉规则）

### 8.3 基础设施能力

1. API Key 认证 + per-IP 速率限制
2. 文件上传校验（MIME、大小、PDF 头部）
3. 节点级超时控制
4. 可选 Celery + Redis 异步任务队列
5. 可选 PostgreSQL 持久化存储
6. 可选 S3/MinIO 对象存储
7. 节点级进度追踪（15%–100%）

### 8.4 测试现状

当前测试：

- 执行命令：`python -m pytest`（或 `make test`）
- 结果：**162 passed, 1 skipped**

覆盖方向包括：

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_auth.py` | API Key 认证（有效/无效/缺失/health 绕过） |
| `test_input_validation.py` | 文件大小、MIME、PDF 头部、文件名清理 |
| `test_ocr.py` | OCR 引擎工厂、PaddleOCR/Tesseract mock、语言检测 |
| `test_render.py` | 页面渲染、DPI、选择性渲染 |
| `test_token_manager.py` | Token 计数、截断、分块、上下文管理 |
| `test_embedding_index.py` | Embedding 索引、RAG 工厂、混合检索 |
| `test_celery_task.py` | Celery 分发、后端切换 |
| `test_pg_store.py` | PostgreSQL CRUD、Protocol 满足、工厂 |
| `test_object_store.py` | S3 对象存储、本地回退 |
| `test_validators.py` / `_extended` | 勾稽校验逻辑 |
| `test_signals.py` / `_extended` | 风险信号触发 |
| `test_schemas.py` | Schema 校验 |
| `test_storage.py` | 本地存储 CRUD |
| `test_pipeline_mock.py` | Mock 管道端到端 |
| `test_vector_index.py` | Token-overlap 检索 |
| `test_nodes_helpers.py` | 节点辅助函数 |
| `test_normalizer_and_events.py` | 科目归一 + 事件研究 |

## 9. 已知限制与当前边界

1. **行情事件研究**：模块已留接口（Dummy + YFinance stubs），尚未并入主分析流程，Tushare/Polygon 提供商待实现。
2. **Golden 测试集**：有 Mock 端到端测试，但尚无真实 PDF 的参考结果对比。
3. **表格解析**：使用 pdfplumber，对于无边框或复杂嵌套表格可能精度有限。
4. **CI/CD**：尚未配置 GitHub Actions。
5. **Docker**：Dockerfile 和 docker-compose 待实现。
6. **Prometheus / OpenTelemetry**：可观测性指标待实现。

## 10. 配置项

`.env.example` 当前支持的全部配置（按功能分组）：

```bash
# ── LLM ──────────────────────────────────────────────────────
OPENAI_API_KEY=                  # OpenAI API Key（留空 = MockLLM）
OPENAI_MODEL=gpt-4.1-mini       # 默认 OpenAI 模型
LLM_TIMEOUT_S=60                 # LLM 调用超时（秒）
MODEL_MAX_TOKENS=128000          # 模型上下文窗口

# ── 多模型路由（P3）─────────────────────────────────────────
LLM_DEFAULT_MODEL=               # 默认 LLM（provider:model 格式）
LLM_EXTRACTION_MODEL=            # 报表抽取使用的模型
LLM_REPORT_MODEL=                # 报告生成使用的模型
ANTHROPIC_API_KEY=               # Anthropic API Key

# ── RAG（P3）─────────────────────────────────────────────────
RAG_MODE=token_overlap           # token_overlap | embedding | hybrid
EMBEDDING_MODEL=auto             # 嵌入模型（auto = 按文档语言选择）

# ── LangSmith 追踪 ──────────────────────────────────────────
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=financial-report-agent

# ── 存储 ─────────────────────────────────────────────────────
DATA_DIR=data                    # 本地输出目录
STORAGE_BACKEND=local            # local | postgres
DATABASE_URL=                    # PostgreSQL 连接 URL

# ── S3/MinIO 对象存储（P4）───────────────────────────────────
S3_ENDPOINT=
S3_BUCKET=jetbot-pdfs
S3_ACCESS_KEY=
S3_SECRET_KEY=

# ── 任务队列（P4）────────────────────────────────────────────
TASK_BACKEND=background          # background | celery
CELERY_BROKER_URL=redis://localhost:6379/0

# ── API 安全 ─────────────────────────────────────────────────
API_KEYS=                        # 逗号分隔的有效 API Key（留空 = 免认证）
CORS_ORIGINS=*
RATE_LIMIT_UPLOAD=5              # 上传接口每分钟限制
RATE_LIMIT_ANALYZE=10            # 分析接口每分钟限制
RATE_LIMIT_READ=60               # 读取接口每分钟限制

# ── 上传限制 ─────────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB=100

# ── 管线超时 ─────────────────────────────────────────────────
NODE_TIMEOUT_S=120               # 每个节点超时（秒）

# ── 调试 ─────────────────────────────────────────────────────
DEBUG=0                          # 1 = 保存中间产物
```

## 11. 结论

当前版本（P1–P4 完成）已具备生产级的财报 PDF 解析与分析能力：

- **安全**：API Key 认证、速率限制、输入校验、节点超时
- **OCR**：PaddleOCR + Tesseract 双引擎，自动语言检测
- **LLM**：OpenAI + Anthropic 双供应商，多模型任务路由，token 溢出保护
- **RAG**：Token-overlap / Embedding (FAISS) / Hybrid 三种检索模式
- **扩展**：Celery 异步队列、PostgreSQL 持久化、S3 对象存储
- **质量**：162 测试覆盖核心功能，Few-shot 提示词优化

后续升级方向（P5–P7）：行情数据集成、Golden 评测集、Prometheus 可观测性、Docker 容器化、CI/CD 管线。
