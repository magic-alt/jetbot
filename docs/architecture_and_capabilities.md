# 财报 PDF Agent 架构与能力说明

## 1. 文档目的

本文档用于说明当前仓库的：

- 软件架构（分层、模块职责、工作流）
- 技术栈与关键依赖
- 当前版本已经达到的效果（可运行能力）
- 已知限制与后续扩展方向

说明基于当前代码实现（`src/` + `tests/`），不是仅基于最初需求文档。

## 2. 系统定位

该项目是一个“财报 PDF 智能解析与交易员分析 Agent”的 MVP 实现，提供两种入口：

- FastAPI 服务：上传 PDF、触发分析、查询结构化结果与报告
- CLI：离线执行单份 PDF 分析并输出结果文件

系统核心目标是：

1. 从财报 PDF 抽取文本与表格
2. 结构化三大表（利润表/资产负债表/现金流量表）
3. 生成关键注释与风险信号
4. 输出带证据引用的 Trader 风格报告

## 3. 总体架构

### 3.1 分层结构

当前代码对应如下分层：

1. 接入层（API/CLI）
- `src/api/main.py`, `src/api/routes.py`
- `src/cli.py`

2. 编排层（LangGraph）
- `src/agent/graph.py`
- `src/agent/nodes.py`
- `src/agent/state.py`

3. PDF 处理层
- `src/pdf/extractor.py`（PyMuPDF 抽文本 + 可选渲染）
- `src/pdf/tables.py`（pdfplumber 表格抽取）
- `src/pdf/ocr.py`（OCR 占位）

4. 财务语义与规则层
- `src/finance/normalizer.py`（科目归一）
- `src/finance/validators.py`（勾稽校验与指标）
- `src/finance/signals.py`（风险信号生成）

5. LLM 抽象层
- `src/llm/base.py`（LLM 接口 + 默认客户端选择）
- `src/llm/mock.py`（无 Key 可运行）
- `src/llm/openai_client.py`（`langchain_openai.ChatOpenAI` + 降级兼容）

6. 存储与任务状态层
- `src/storage/local_store.py`（本地文件持久化）
- `src/storage/task_store.py`（`tasks.json` 任务状态）
- `src/storage/vector_index.py`（Chunk/Table 检索上下文，RAG 层）

7. 公共工具层
- `src/utils/logging.py`, `src/utils/ids.py`, `src/utils/time.py`

### 3.2 工作流（LangGraph）

状态模型：`AgentState`（`src/agent/state.py`），核心字段包括：

- `pages/chunks/tables/statements/notes/risk_signals/trader_report`
- `validation_results/errors/debug`
- `retry_count/needs_ocr`

执行链路（`src/agent/graph.py`）：

1. `ingest_pdf`
2. `extract_tables`
3. `detect_sections_and_chunk`
4. `extract_financial_statements`
5. `validate_and_reconcile`
6. 条件分支：
- 若出现严重校验问题且重试次数 `< 2`，回到 `extract_financial_statements`
- 否则继续
7. `extract_key_notes`
8. `generate_risk_signals`
9. `build_trader_report`
10. `finalize`

该设计实现了 MVP 级“可重试、可追踪”的有状态工作流。

## 4. 技术栈

来自 `pyproject.toml` 的当前核心技术栈如下：

- Python `>=3.12`
- Web/API：`FastAPI` + `Uvicorn`
- 编排：`LangGraph`
- Schema：`Pydantic v2`
- CLI：`Typer`
- PDF：`PyMuPDF`, `pdfplumber`
- 数据计算：`pandas`
- LLM：`openai` SDK + 本地 `MockLLM`
- LangChain 能力层：`langchain`, `langchain-core`, `langchain-openai`, `langchain-text-splitters`
- 日志：`logging`（自定义 `ContextLoggerAdapter`）
- 测试：`pytest`

运行入口：

- 开发服务：`make dev`
- 测试：`python -m pytest`
- CLI 分析：`python -m src.cli analyze --pdf <file> --out data`

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
3. 当上游抽取证据不足时，节点会填充 fallback evidence，避免出现“完全无引用”的结果

## 6. API 与 CLI 能力

### 6.1 API（`/v1`）

已实现接口：

- `POST /documents`：上传 PDF，创建 `doc_id`
- `POST /documents/{doc_id}/analyze`：后台触发分析
- `GET /documents/{doc_id}`：文档元信息 + 任务状态
- `GET /documents/{doc_id}/report`：TraderReport JSON
- `GET /documents/{doc_id}/report.md`：Markdown 报告
- `GET /documents/{doc_id}/statements`：三大表 JSON
- `GET /documents/{doc_id}/notes`：关键注释
- `GET /documents/{doc_id}/risk-signals`：风险信号

返回结构采用统一 envelope：

- 成功：`{"ok": true, "data": ..., "error": null}`
- 失败：`{"ok": false, "data": null, "error": {"code": "...", "message": "..."}}`

### 6.2 CLI

已实现命令（`python -m src.cli --help`）：

- `analyze`
- `render-report`
- `show`

支持在本地直接触发完整流程并打印结果路径。

## 7. 输出与存储布局

本地存储默认在 `data/`，单文档目录结构如下：

- `data/{doc_id}/raw.pdf`
- `data/{doc_id}/meta.json`
- `data/{doc_id}/extracted/pages.json`
- `data/{doc_id}/extracted/tables.json`
- `data/{doc_id}/extracted/statements.json`
- `data/{doc_id}/extracted/notes.json`
- `data/{doc_id}/extracted/risk_signals.json`
- `data/{doc_id}/report/trader_report.json`
- `data/{doc_id}/report/trader_report.md`

任务状态保存在：

- `data/tasks.json`

## 8. 当前已达到的效果（基于代码与测试）

### 8.1 可运行性

1. API 服务可启动并提供完整接口链路
2. CLI 可执行分析命令并产出报告文件
3. 未配置 `OPENAI_API_KEY` 时可走 `MockLLM` 跑通全链路
4. 配置 OpenAI Key 后可切换到真实模型客户端

### 8.2 处理能力

1. PDF 页级文本抽取与可选页面渲染
2. 表格候选抽取并转结构化 `Table`
3. 三大表抽取：规则识别 + LLM 兜底
4. 勾稽与一致性校验（资产负债平衡、单位一致性、关键字段完整性等）
5. 规则化风险信号生成（如现金流与利润背离、披露不一致等）
6. 节点内使用 `ChatPromptTemplate + with_structured_output`
7. 在关键节点使用 `RunnableParallel` 并行 LLM 分支
8. 通过本地检索层（RAG）组装上下文后生成 JSON + Markdown Trader 报告

### 8.3 测试现状

当前测试可通过：

- 执行命令：`python -m pytest`
- 结果：`5 passed`（本地验证）

覆盖方向包括：

- Schema 校验
- 财务校验逻辑
- 风险信号触发
- Mock 管道端到端跑通

## 9. 已知限制与当前边界

1. OCR 仍是占位实现（`src/pdf/ocr.py`），扫描版 PDF 识别能力未真正接入。
2. 行情事件研究模块已留接口，但尚未并入主分析流程。
3. API 后台任务为进程内任务 + 本地 JSON 状态，不是分布式任务系统。
4. 部分中文关键词目前是占位符（字面 `?`），会影响中文科目归一和规则匹配准确度。
5. 表格解析、章节识别和提示词仍为 MVP 粒度，对复杂版式财报的鲁棒性有限。

## 10. 配置项

`.env.example` 当前支持：

- `OPENAI_API_KEY=`
- `OPENAI_MODEL=gpt-4.1-mini`
- `LANGSMITH_TRACING=true`
- `LANGSMITH_API_KEY=`
- `LANGSMITH_PROJECT=financial-report-agent`
- `DATA_DIR=data`
- `DEBUG=0`

其中 `DEBUG=1` 时，流程会保存更多中间产物用于排查。

## 11. 结论

当前版本已经具备“可运行的财报 PDF 解析与分析闭环”，可完成上传/解析/校验/信号/报告输出的 MVP 主流程，并具备 Mock/真实 LLM 双模式能力。  
同时，在 OCR、中文关键词质量、复杂报表鲁棒性和任务调度能力上仍有明确改进空间，适合进入下一轮工程化增强。
