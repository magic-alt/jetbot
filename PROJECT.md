
---

# ✅ 给 Codex 的输入：软件设计需求与实现指令（请按此生成完整代码仓库）

## 0. 角色与输出要求

你是一个资深 Python 架构师 + 全栈工程师。请生成一个可运行的 Git 仓库，实现一个“财报 PDF 智能解析与交易员分析 Agent”系统。

**输出要求：**

1. 生成完整项目目录结构、可运行代码、README、示例配置、必要的测试用例。
2. 提供 `make dev` 或等价脚本能启动 API 服务；提供 CLI 能本地跑一份 PDF 并输出结果。
3. 代码遵循工程规范：类型注解、日志、错误处理、分层架构、可扩展接口。
4. 允许无外部依赖模式运行：不配置大模型时用 `MockLLM` 返回占位结果；配置后使用真实 LLM。
5. **所有分析输出必须携带证据引用**：至少给出页码、文本片段 id，必要时包含表格 id。
6. 不提供任何具体股票的投资建议；只输出分析框架与计算结果（以免责声明形式写入报告）。

---

## 1. 产品目标与范围

### 1.1 核心目标（MVP）

* 输入：PDF（财报/年报/季报，中文为主，允许英文）
* 输出：

  1. 文档结构化：按页、章节、段落、表格拆解
  2. 三大表结构化抽取：利润表、资产负债表、现金流量表
  3. 关键注释抽取：会计政策、重大估计、关联交易、减值、或有事项、分部信息、审计意见（如有）
  4. 勾稽校验与一致性检查：资产=负债+权益、净利润与经营现金流背离等
  5. Trader 视角摘要：预期差框架、关键驱动、风险信号、要点清单
  6. 财报质量/真实性风险信号：不判“真/假”，输出“风险信号 + 证据链 + 解释”
* 提供 API + CLI：

  * API：上传 PDF、触发解析、查询任务状态、获取结构化结果、获取报告
  * CLI：`analyze --pdf xxx.pdf --out out_dir`

### 1.2 扩展目标（v1）

* 支持 OCR（扫描版 PDF）
* 支持向量检索（RAG）：问答/回查引用
* 支持股价事件研究（需要行情数据源接口）
* 支持评测集与回归测试（golden set）

### 1.3 非目标（明确不做）

* 不做自动交易/下单
* 不做“断言造假”的法律结论，仅做“风险信号”
* 不保证对所有 PDF 模版 100% 抽取准确（需评测迭代）

---

## 2. 总体架构（分层 + 可替换）

### 2.1 模块分层

1. **Ingestion 层**：PDF 读取、页渲染、文本抽取、表格候选抽取、是否扫描件检测
2. **Structuring 层**：章节识别、块（chunk）切分、表格解析为结构化表
3. **Financial Extraction 层**：三大表字段映射与标准化（科目归一、单位/币种识别）
4. **Validation 层**：勾稽校验、合计校验、同比环比重算、单位一致性
5. **LLM Agent 层（LangGraph）**：多步编排（抽取→校验→回查→重试→报告）
6. **Storage 层**：元数据、结构化结果、报告、向量索引（可选）
7. **API/CLI 层**：触发任务与获取结果

### 2.2 编排框架选择

* 使用 **LangGraph** 实现状态机式工作流（可循环、可分支、可重试）。
* LLM 调用抽象为 `LLMClient` 接口，可用 OpenAI 或其他模型实现；默认带 `MockLLMClient`。

---

## 3. 技术栈与依赖

### 3.1 Python 与框架

* Python 3.12+
* FastAPI + Uvicorn（API 服务）
* Pydantic v2（schema）
* LangGraph（工作流编排）
* 日志：structlog 或标准 logging（可选 structlog）
* 任务执行（MVP）：内置后台任务/线程池；v1：Celery/RQ（可选）

### 3.2 PDF 处理

* PyMuPDF（fitz）：文本抽取、页渲染、坐标信息（注意许可证：商业用途需评估合规）
* pdfplumber：表格/线条/字符粒度信息
* 可选：unstructured（分块/元素抽取）

### 3.3 存储

* MVP：本地文件系统 + SQLite（或纯 JSON 文件）
* v1：Postgres + 对象存储（MinIO/S3）+ 向量库（Qdrant/FAISS）

### 3.4 OCR（可选）

* MVP：提供接口与占位实现（不强依赖）
* v1：PaddleOCR（中文）或 Tesseract（英文）

### 3.5 行情数据（可选）

* 定义 `MarketDataProvider` 抽象接口
* MVP 提供 `DummyMarketDataProvider`（返回空）
* v1 可接入 yfinance/Polygon/Tushare（由用户填 key）

---

## 4. 数据模型（必须实现的 Pydantic Schema）

请创建 `src/schemas/` 下的 pydantic models（v2），包含最少字段如下。

### 4.1 文档与块

* `DocumentMeta`:

  * `doc_id: str`
  * `filename: str`
  * `company: str | None`
  * `period_end: date | None`（报告期）
  * `report_type: str | None`（年报/季报/半年报/10-K 等）
  * `language: str | None`
  * `created_at: datetime`
* `Page`:

  * `page_number: int`
  * `text: str`
  * `images: list[str]`（页渲染图片路径，可选）
* `Chunk`:

  * `chunk_id: str`
  * `page_start: int`
  * `page_end: int`
  * `section: str | None`
  * `text: str`
  * `bbox: tuple[float,float,float,float] | None`（可选）
  * `source_refs: list[SourceRef]`
* `SourceRef`:

  * `ref_type: Literal["page_text","table","image"]`
  * `page: int`
  * `table_id: str | None`
  * `quote: str | None`（最多 200 字）
  * `confidence: float`（0~1）

### 4.2 表格结构

* `TableCell`:

  * `row: int`
  * `col: int`
  * `text: str`
* `Table`:

  * `table_id: str`
  * `page: int`
  * `title: str | None`
  * `cells: list[TableCell]`
  * `n_rows: int`
  * `n_cols: int`
  * `raw_markdown: str | None`（便于调试）
  * `source_refs: list[SourceRef]`

### 4.3 三大表统一结构

* `StatementLineItem`:

  * `name_raw: str`
  * `name_norm: str`（归一化科目名）
  * `value_current: float | None`
  * `value_prior: float | None`
  * `unit: str | None`（元/千元/万元/百万/十亿）
  * `currency: str | None`（CNY/HKD/USD…）
  * `notes: str | None`
  * `source_refs: list[SourceRef]`
* `FinancialStatement`:

  * `statement_type: Literal["income","balance","cashflow"]`
  * `period_end: date | None`
  * `period_start: date | None`
  * `line_items: list[StatementLineItem]`
  * `totals: dict[str, float]`（如 total_assets / net_income 等）
  * `extraction_confidence: float`
  * `issues: list[str]`（抽取警告）

### 4.4 注释与风险信号

* `KeyNote`:

  * `note_type: Literal["accounting_policy","audit_opinion","related_party","impairment","contingency","segment","guidance","other"]`
  * `summary: str`
  * `source_refs: list[SourceRef]`
* `RiskSignal`:

  * `signal_id: str`
  * `category: Literal["cash_vs_profit","accruals","one_offs","audit_governance","disclosure_inconsistency","working_capital","other"]`
  * `title: str`
  * `severity: Literal["low","medium","high"]`
  * `description: str`
  * `metrics: dict[str, float | str]`
  * `evidence: list[SourceRef]`
* `TraderReport`:

  * `doc_id: str`
  * `executive_summary: str`
  * `key_drivers: list[str]`
  * `numbers_snapshot: dict[str, float]`
  * `risk_signals: list[RiskSignal]`
  * `notes: list[KeyNote]`
  * `limitations: list[str]`（免责声明/局限）
  * `created_at: datetime`

### 4.5 事件研究（可选）

* `EventStudyResult`:

  * `event_date: date`
  * `window: tuple[int,int]`（如 -3,+3）
  * `returns: dict[str, float]`（例如 cumulative_return, abnormal_return 等）
  * `volatility: dict[str, float]`
  * `volume: dict[str, float]`
  * `data_source: str`

---

## 5. LangGraph 工作流（必须实现）

### 5.1 状态 State

创建 `AgentState`（pydantic 或 TypedDict）：

* `doc_meta: DocumentMeta`
* `pages: list[Page]`
* `chunks: list[Chunk]`
* `tables: list[Table]`
* `statements: dict[str, FinancialStatement]`（income/balance/cashflow）
* `notes: list[KeyNote]`
* `validation_results: dict[str, Any]`
* `risk_signals: list[RiskSignal]`
* `trader_report: TraderReport | None`
* `errors: list[str]`
* `debug: dict[str, Any]`

### 5.2 节点 Nodes 与逻辑

实现以下节点函数（放 `src/agent/nodes.py`）：

1. `ingest_pdf(state) -> state`

   * 读取 PDF，抽每页文本（PyMuPDF），保存页渲染图（可选）
   * 判断是否扫描件：若某页文本过少且图片占比高 → 标记 `needs_ocr=True`
2. `extract_tables(state) -> state`

   * 用 pdfplumber 抽取表格候选（至少抽取含数字密集的区域）
3. `detect_sections_and_chunk(state) -> state`

   * 基于标题模式/字体大小/正则（如“一、二、三、（一）”）做章节粗分
   * chunk 策略：按章节 + 页边界，目标 800~1500 字/块
4. `extract_financial_statements(state) -> state`

   * 从 tables + chunks 中定位三大表
   * 先用规则：关键词（资产负债表/利润表/现金流量表/合并…）
   * 再用 LLM 做结构化映射输出到 `FinancialStatement`
5. `validate_and_reconcile(state) -> state`

   * 勾稽校验：

     * balance: total_assets ≈ total_liabilities + total_equity（允许一定误差）
     * income: revenue, gross_profit, net_income 等关键字段存在性
     * cashflow: operating_cf 与 net_income 的偏离指标
   * 生成 `validation_results` + issues；若严重失败，写入 `errors` 并触发重试分支
6. `extract_key_notes(state) -> state`

   * 从 chunks 中抽取关键注释（LLM 结构化输出 `KeyNote`）
7. `generate_risk_signals(state) -> state`

   * 规则 + LLM：

     * 规则先算指标（应收/存货/经营现金流/净利润/一次性项目等）
     * LLM 解释原因并关联证据引用
   * 输出 `RiskSignal[]`
8. `build_trader_report(state) -> state`

   * 生成 trader 风格报告：要点、数字快照、驱动因素、风险信号、引用证据、免责声明
9. `finalize(state) -> state`

   * 持久化：写 JSON 到 `data/{doc_id}/`（MVP）
   * 返回最终报告

### 5.3 流程图（逻辑）

* start → ingest_pdf → extract_tables → detect_sections_and_chunk → extract_financial_statements → validate_and_reconcile

  * if 严重失败且重试次数 < 2：回到 extract_financial_statements（把失败原因塞到 prompt）
  * else：extract_key_notes → generate_risk_signals → build_trader_report → finalize → end

---

## 6. LLM 交互规范（必须实现可替换）

### 6.1 接口

在 `src/llm/base.py`：

* `class LLMClient(Protocol):`

  * `async def chat(self, system: str, user: str, json_schema: dict | None = None) -> str: ...`

实现：

* `MockLLMClient`：返回固定 JSON（用于无 key 运行）
* `OpenAILLMClient`：读取环境变量：

  * `OPENAI_API_KEY`
  * `OPENAI_MODEL`（默认如 `gpt-4.1-mini` 或占位）
  * 支持“结构化输出”：若给 `json_schema`，则强制模型输出 JSON 并做 parse/validate

### 6.2 Prompt 模板（必须落地）

放到 `src/prompts/`，至少三套：

1. `statement_extraction_prompt.md`
2. `key_notes_prompt.md`
3. `trader_report_prompt.md`

要求：

* 明确输出 JSON schema
* 明确“必须提供 source_refs（页码/表格 id/引用片段）”
* 明确单位币种处理规则
* 明确不确定时要填 `issues`、降低 `extraction_confidence`

---

## 7. 校验与计算（必须实现的规则）

在 `src/finance/validators.py` 实现：

### 7.1 基本勾稽

* 资产负债表：`abs(total_assets - (total_liabilities + total_equity)) / max(total_assets,1) < 0.02` 视为通过（阈值可配置）
* 表内合计：若存在“合计/总计”，检查分项加总误差
* 单位一致性：同一张表必须单位一致，否则 issue

### 7.2 盈利与现金流背离指标

* `profit_to_cfo_ratio = operating_cf / max(net_income, 1e-6)`
* `ar_growth_vs_rev_growth`（若能取到应收与收入两期）

### 7.3 风险信号触发规则（MVP）

至少实现以下信号（可配置阈值）：

* `cash_vs_profit`: 净利润为正但经营现金流为负（medium/high）
* `working_capital`: 应收或存货增长显著高于收入（medium）
* `disclosure_inconsistency`: 三表勾稽失败或单位混乱（high）
* `audit_governance`: 若文本出现“保留意见/无法表示意见/否定意见/强调事项”等关键词（medium/high，取决于关键词）

每个信号必须包含：

* 指标数值 metrics
* 引用 evidence（页码/引用片段/表格）

---

## 8. 股价事件研究模块（可选，但要留接口）

在 `src/market/`：

### 8.1 接口

`class MarketDataProvider(Protocol):`

* `get_prices(ticker: str, start: date, end: date) -> pd.DataFrame`
* `get_volume(...)`

实现：

* `DummyMarketDataProvider`：返回空 df
* `YFinanceMarketDataProvider`（可选实现；若无依赖则不启用）

### 8.2 事件研究计算

在 `src/market/event_study.py`：

* 输入：事件日、窗口（-3,+3）、价格序列
* 输出：累计收益、波动变化、成交量异常（相对前 N 日均值）

报告中若无行情数据：写入 limitations

---

## 9. 存储与文件布局（MVP 必须实现）

### 9.1 本地文件

* `data/{doc_id}/raw.pdf`
* `data/{doc_id}/pages/page_0001.png`（可选）
* `data/{doc_id}/extracted/pages.json`
* `data/{doc_id}/extracted/tables.json`
* `data/{doc_id}/extracted/statements.json`
* `data/{doc_id}/extracted/notes.json`
* `data/{doc_id}/extracted/risk_signals.json`
* `data/{doc_id}/report/trader_report.json`
* `data/{doc_id}/report/trader_report.md`

### 9.2 任务状态

实现简单任务表（SQLite）或 json：

* `doc_id`, `status`（queued/running/succeeded/failed）
* `progress`（0~100）
* `error_message`

---

## 10. API 设计（FastAPI 必须实现）

在 `src/api/main.py`：

* `POST /v1/documents`：上传 PDF（multipart），返回 `doc_id`
* `POST /v1/documents/{doc_id}/analyze`：触发分析（后台任务），返回任务状态
* `GET /v1/documents/{doc_id}`：返回文档元信息与状态
* `GET /v1/documents/{doc_id}/report`：返回 TraderReport（JSON）
* `GET /v1/documents/{doc_id}/report.md`：返回 markdown 报告
* `GET /v1/documents/{doc_id}/statements`：返回三大表结构化 JSON
* `GET /v1/documents/{doc_id}/notes`：返回关键注释
* `GET /v1/documents/{doc_id}/risk-signals`：返回风险信号

要求：

* 所有接口返回统一 envelope：`{ "ok": bool, "data": ..., "error": ... }`
* 错误要有错误码与可读 message
* 支持 CORS（可选）

---

## 11. CLI 设计（必须实现）

在 `src/cli.py` 使用 typer 或 argparse：

* `analyze --pdf path/to.pdf --out data/ --company "xxx" --period-end 2025-12-31`
* `render-report --doc-id ...`
* `show --doc-id ... --what report|signals|statements`

CLI 输出：

* 控制台打印关键进度
* 最终打印报告文件路径

---

## 12. 可观测性与调试（必须实现）

* 日志必须包含：`doc_id`, `node_name`, `elapsed_ms`
* 每个节点输出写入 `state.debug`（只放轻量信息）
* 提供 `DEBUG=1` 时保存中间产物（如每步抽取结果）

---

## 13. 测试与评测（必须实现最小集）

### 13.1 单元测试（pytest）

* validators 勾稽逻辑
* schema 校验
* risk signal 触发逻辑

### 13.2 Golden 测试（MVP）

在 `tests/fixtures/` 放 1~2 个小 PDF（或用文本模拟），保证：

* pipeline 能跑通
* 输出 JSON 结构稳定

（如果无法内嵌 PDF，可用 `FakePDFExtractor` 让测试不依赖真实 PDF）

---

## 14. 项目结构（必须按此生成）

```
repo/
  README.md
  pyproject.toml
  .env.example
  Makefile
  src/
    api/
      main.py
      routes.py
    agent/
      graph.py
      nodes.py
      state.py
    pdf/
      extractor.py
      tables.py
      ocr.py
      render.py
    finance/
      schemas.py
      normalizer.py
      validators.py
      signals.py
    market/
      provider.py
      event_study.py
    llm/
      base.py
      mock.py
      openai_client.py
    prompts/
      statement_extraction_prompt.md
      key_notes_prompt.md
      trader_report_prompt.md
    storage/
      local_store.py
      task_store.py
    utils/
      logging.py
      ids.py
      time.py
    cli.py
  tests/
    test_validators.py
    test_signals.py
    test_pipeline_mock.py
  data/  (gitignore)
```

---

## 15. README 必须包含

* 快速开始（本地跑 mock）
* 配置 OpenAI key 后如何跑真实模型
* API 示例（curl）
* CLI 示例
* 输出文件说明
* 免责声明（Not financial advice）

---

## 16. 验收标准（必须满足）

1. `make dev` 启动后可上传 PDF 并触发分析，最终能 `GET report.md`
2. 未配置 OPENAI key 也能跑通（mock 模式），输出结构完整
3. 报告中每个关键结论至少包含 1 条 `SourceRef`（页码/引用）
4. 勾稽校验与风险信号至少能输出 2 类信号
5. 单元测试通过

---

## 17. 重要实现细节（强制）

* 对 LLM 输出必须 `json.loads` + pydantic validate，失败则重试 1 次并降低置信度
* 任何数字字段必须可追溯到表格/页文本引用
* 防止幻觉：模型不能“编造数据”，若缺失必须写 `None` 并在 issues 说明
* 对 PDF 解析异常要降级：提取不到表格时仍可仅基于正文生成 notes 与框架性报告（limitations 写清楚）

---

# 实现开始：请生成上述仓库的全部代码与文件

（到此为止）

---

