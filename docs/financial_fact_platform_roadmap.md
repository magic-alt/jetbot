# Jetbot Financial Fact Platform 技术路线图

## 1. 背景与结论

Jetbot 当前已经具备较完整的财报 PDF Agent MVP 能力：PDF 上传、文本与表格抽取、三大表结构化、基础勾稽校验、关键注释、风险信号、深度分析、前端查看、Docker 化部署和黄金用例测试。下一阶段的主要瓶颈不是继续增加泛化 Agent 功能，而是把系统做成可被分析师、审计/咨询、投研数据团队信任的事实抽取平台。

推荐方向是 **Filing-to-Model Copilot**：从财报、10-K、10-Q、PDF、HTML、XBRL 中抽取可审计、可复核、可导出的 canonical financial facts，并用页码、表格、单元格、bbox、原文 quote 和引擎 trace 形成完整证据链。

核心路线：

1. 建立真实 benchmark 和可量化质量门槛。
2. 建立 canonical financial fact schema 和证据模型。
3. 把当前 `FinancialStatement` 输出转换并持久化为事实层。
4. 增加人工复核与修正闭环。
5. 扩展 PDF/HTML/XBRL 多源 ingestion 和表格多引擎 router。
6. 输出 Excel、CSV、JSON 和 API，服务 analyst workflow。

## 2. 产品定位

### 2.1 推荐首个产品楔子

首个商业化/试点方向建议锁定为：

**美股 10-K / 10-Q Filing-to-Model Copilot**

目标用户：

- 买方/卖方分析师：需要快速把 filing 转成模型输入。
- 审计、咨询、投行助理：需要可追溯的事实抽取和复核。
- 数据/量化团队：需要标准化事实 API 和可校验证据。

首屏价值：

- 上传或输入 filing。
- 自动提取三大表和关键事实。
- 每个事实可跳转到原始证据。
- 支持人工修正。
- 导出 evidence-linked Excel / CSV / JSON。

### 2.2 暂不优先做的功能

以下能力可以作为 P1/P2，但不应阻塞 P0：

- 泛聊天式财报问答。
- 自动投资建议或交易结论。
- 多 Agent 辩论。
- PPT 自动生成。
- 大规模同业对比。
- 租户计费、CRM、watchlist 等 SaaS 外围能力。

原因：当前阶段最重要的是事实准确率、证据链、人工复核和 benchmark。没有这些底座，更多 Agent 输出会放大不可信问题。

## 3. 当前能力基线

### 3.1 已具备能力

- API/CLI：`src/api/`、`src/cli.py`。
- LangGraph pipeline：`src/agent/graph.py`、`src/agent/nodes.py`。
- PDF 引擎：PyMuPDF / PDFium 抽象位于 `src/pdf/engine.py`。
- 表格抽取：pdfplumber 位于 `src/pdf/tables.py`。
- OCR：PaddleOCR/Tesseract abstraction 位于 `src/pdf/ocr.py`。
- LLM provider routing：OpenAI、Anthropic、DeepSeek、Ollama、mock 位于 `src/llm/`。
- 财务校验：`src/finance/validators.py`。
- 风险信号：`src/finance/signals.py`。
- 前端工作台：`web/src/views/DocumentDashboard.vue`。
- PDFium 页面预览：`web/src/components/PdfViewer.vue`。
- Golden tests 和 metrics：`tests/golden/`、`src/utils/metrics.py`、`scripts/eval.py`。

### 3.2 主要缺口

- `SourceRef` 原本只有 page/table/quote/confidence，不能精确到 row/col/bbox/engine/artifact。
- 表格单元格缺少 bbox、rowspan、colspan、engine 和 confidence。
- 没有一等公民 `FinancialFact`，三大表输出无法直接支撑 Excel/API 和人工修正。
- 没有 correction audit log。
- OCR 已能产生 bbox，但 pipeline 中被压平成文本，证据粒度丢失。
- `scripts/eval.py` 原本只是跑 pytest，没有机器可读评测报告和 fact-level metrics。
- 前端 evidence click 只能跳页，不能高亮具体 bbox 或表格单元格。
- 还没有 SEC/XBRL/HTML ingestion，也没有表格多引擎 router。

## 4. 已完成的第一实现切片

本路线图的第一切片已通过 PR12 合并到 `main`，目标是为后续人工复核、导出和 benchmark 建立事实层底座。

### 4.1 Schema 与证据模型

已在 `src/schemas/models.py` 中完成：

- 扩展 `SourceRef`：`row`、`col`、`bbox`、`engine`、`artifact_path`。
- 扩展 `TableCell`：`rowspan`、`colspan`、`bbox`、`confidence`、`engine`。
- 新增 `FinancialFact`：承载 canonical concept、raw label、value、unit、scale、currency、period、source_refs、confidence、extraction_engine、metadata。
- 新增 `ExtractionTrace`：记录引擎、stage、status、耗时、metrics、source_refs 和错误。
- 新增 `Correction`：记录 fact 字段修正、old/new value、actor、reason、timestamp 和证据。

兼容策略：新增字段均为 optional 或有默认值，避免破坏旧 API 和旧 JSON。

### 4.2 Canonical facts 转换层

已新增 `src/finance/facts.py`：

- `facts_from_statements(doc_id, statements)`：把当前 `FinancialStatement` 转换为 `FinancialFact`。
- `apply_corrections(facts, corrections)`：根据 correction 生成 effective facts。
- 自动保留 line item evidence。
- 自动推断 period type：balance 为 `instant`，income/cashflow 为 `duration`。
- 自动从 unit 推断 scale，例如 USD millions -> 1,000,000。
- 使用稳定 hash 生成 `fact_id`，便于后续 correction 绑定。

### 4.3 Pipeline 持久化

已更新：

- `src/agent/state.py`：新增 `facts`、`corrections`、`extraction_traces`。
- `src/agent/nodes.py`：`finalize()` 阶段自动生成并保存 `extracted/facts.json`。
- `_save_partial_results()`：失败时如已有 facts 也会保存 partial facts。

### 4.4 API 与前端类型

已更新：

- `src/api/routes.py`：新增 `GET /v1/documents/{doc_id}/facts`。
- `web/src/api/types.ts`：新增 `FinancialFact` 类型，扩展 `SourceRef` 和 `TableCell`。
- `web/src/api/docs.ts`：新增 `docsApi.facts(docId)`，并规范化 richer source refs。

### 4.5 Eval 与指标

已更新：

- `src/utils/metrics.py`：新增 `fact_value_accuracy()`、`fact_source_ref_completeness()`，并接入 `compute_golden_metrics()`。
- `scripts/eval.py`：升级为评测 runner，可执行 golden cases，输出 `eval_report.json` 和 `eval_report.md`。
- 默认强制 mock LLM，避免评测误打真实 API。
- 支持 `--skip-pytest` 和 `--output-dir`。

### 4.6 测试覆盖

已新增/更新：

- `tests/test_finance_facts.py`：覆盖 fact 转换、证据保留、total fallback、correction 应用。
- `tests/test_eval_script.py`：覆盖 eval report 写入与失败状态。
- `tests/test_metrics.py`：覆盖 fact-level metrics。
- `tests/test_routes_web.py`：覆盖 facts endpoint。

## 5. 90 天技术路线

### Phase 0：产品聚焦与质量门槛，Week 0-1

目标：明确只为可信 fact extraction 服务，不让泛 Agent 功能分散优先级。

交付项：

1. 固化首个 ICP：US 10-K / 10-Q analyst workflow。
2. 明确 P0 输出：facts、evidence、review、Excel/API。
3. 定义质量门槛：
   - 关键 facts 数值准确率。
   - line-item precision/recall/F1。
   - source-ref completeness。
   - bbox/cell evidence coverage。
   - balance equation pass rate。
   - 人工复核平均耗时。
   - 每文档成本与耗时。
4. 建立 benchmark 数据政策：真实 PDF 与人工标签默认不入 git，只提交 manifest、匿名标签、合成 fixture 和指标结果。

验收标准：

- 文档和 README 中明确 Jetbot 的下一阶段定位。
- 每个 P0 feature 都能映射到质量指标。
- 不把真实敏感 PDF 提交到仓库；真实样本只保存在本地或私有存储，仓库只提交 manifest、匿名标签、合成 fixture、schema 和阈值配置。

### Phase 1：Benchmark 与 Eval CI，Week 1-2

目标：先能度量，再谈优化。

交付项：

1. 扩展 `tests/golden/`：保留合成 deterministic cases。
2. 新增 benchmark manifest schema：
   - document id。
   - source type。
   - expected facts。
   - expected evidence。
   - expected notes。
   - expected risk labels。
3. 扩展 `scripts/eval.py`：
   - 支持本地 benchmark dataset。
   - 输出 JSON/Markdown。
   - 支持阈值 gate。
   - 支持 CI-friendly exit code。
4. 首批 benchmark：
   - 20 个 US 10-K/10-Q。
   - 10 个 HK/A-share/Japan PDF 作为 stretch。
   - 10 个扫描件/复杂表格 PDF 作为 stress cases。
5. 先围绕 10 个关键 facts 建立准确率：revenue、gross profit、operating income、net income、total assets、total liabilities、total equity、operating cash flow、capex、cash and equivalents。

验收标准：

- `python scripts/eval.py --output-dir data/eval-dev` 可生成报告。
- `python scripts/eval.py --thresholds benchmarks/thresholds/golden_minimum.json` 可作为质量门槛，指标低于阈值时返回非 0。
- 报告包含 document-level 与 aggregate metrics。
- synthetic golden gate 可稳定在 CI 中运行。
- real PDF benchmark 可本地运行，且不会把敏感样本提交到 git。

### Phase 2：Canonical Fact Schema 与证据模型，Week 2-4

目标：把 Jetbot 的主输出从 report 转成 facts + evidence。

交付项：

1. 完善 `FinancialFact`：
   - company、ticker、CIK、filing type。
   - statement type。
   - canonical concept。
   - raw label。
   - value、unit、scale、currency。
   - period start/end、period type。
   - confidence。
   - extraction engine。
   - source refs。
2. 完善 `SourceRef`：
   - page。
   - table_id。
   - row/col。
   - bbox。
   - quote。
   - artifact path。
   - engine。
   - confidence。
3. 增加 fact validation：
   - missing critical facts。
   - duplicate concepts。
   - period consistency。
   - scale/currency consistency。
   - balance equation。
   - cashflow reconciliation。
4. 将 facts 作为 API 和导出的主数据结构。

验收标准：

- 所有关键 facts 都能带至少一个 source ref。
- evidence fields 在 API 和前端类型中一致。
- 旧 `FinancialStatement` API 继续兼容。
- facts 能在 pipeline 成功和 partial failure 时保存。

### Phase 3：Evidence Review 与人工修正，Week 3-5

目标：让用户能复核、修正、沉淀 ground truth。

交付项：

1. 后端 correction endpoints：
   - `GET /v1/documents/{doc_id}/corrections`。
   - `POST /v1/documents/{doc_id}/facts/{fact_id}/corrections`。
   - `GET /v1/documents/{doc_id}/facts/effective`。
2. 前端 review workspace：
   - 左侧 PDFium page image。
   - 右侧 facts/table/statements。
   - 点击 fact 跳页并高亮 bbox/cell。
3. `PdfViewer` overlay：
   - bbox 坐标归一化。
   - DPI 改变时仍能正确映射。
   - 支持多个高亮。
4. `EvidenceLink` 扩展：
   - 显示 page/table/row/col。
   - tooltip 展示 quote 和 engine。
5. Correction audit：
   - actor。
   - timestamp。
   - old/new value。
   - reason。
   - source_refs。
6. 修正结果回流 eval dataset。

验收标准：

- 用户能修正 value、concept、unit、period、evidence。
- 修正后 facts/export/API 一致。
- correction history 不丢失。
- 点击证据不会触发浏览器下载或新窗口弹窗。

### Phase 4：表格多引擎 Router，Week 5-7

目标：从单一 pdfplumber 升级为可评测、可回退的多引擎表格抽取层。

交付项：

1. 新增 `TableExtractor` protocol。
2. 将 pdfplumber 包成默认 extractor。
3. 增加可选 extractor：
   - Camelot：适合 ruled tables。
   - Docling/Marker：适合 layout-heavy PDFs。
   - OCR layout：适合扫描件。
   - LLM vision fallback：仅用于低置信度关键表。
4. 新增 router：
   - 根据 text density、page image、table confidence、OCR need、page rotation、statement section 选择引擎。
5. 扩展 `Table`/`TableCell`：
   - bbox。
   - rowspan/colspan。
   - engine。
   - confidence。
   - extraction settings。
6. 新增 table-level metrics：
   - table recall。
   - cell exact match。
   - numeric match。
   - critical fact recovery rate。

验收标准：

- 每个 engine adapter 输出统一 `Table` schema。
- router 选择路径可解释并记录 trace。
- 低置信度表格有 fallback 机制。
- eval report 能按 engine 统计表现。

### Phase 5：SEC/XBRL/HTML Ingestion 与 Taxonomy，Week 7-9

目标：优先使用结构化来源，降低 PDF 抽取不确定性。

交付项：

1. 新增 `src/filings/`：
   - SEC ticker/CIK lookup。
   - filing manifest download。
   - HTML tables parsing。
   - XBRL facts extraction。
2. 定义 source priority：
   - XBRL/HTML。
   - PDF text layer。
   - PDF table extraction。
   - OCR/layout。
   - LLM fallback。
3. 新增 `src/finance/taxonomy.py`：
   - revenue。
   - cost_of_revenue。
   - gross_profit。
   - operating_expense。
   - operating_income。
   - interest_expense。
   - pretax_income。
   - income_tax。
   - net_income。
   - EPS。
   - cash。
   - receivables。
   - inventory。
   - total_assets。
   - debt。
   - total_liabilities。
   - total_equity。
   - CFO。
   - capex。
   - FCF。
4. Raw label mapping：
   - deterministic aliases first。
   - LLM-assisted mapping only for low confidence。
   - preserve raw label and mapping evidence。
5. Period/scale/currency normalization：
   - US GAAP。
   - IFRS。
   - Chinese labels。

验收标准：

- SEC/XBRL fixtures 全部 network-free。
- 同一 document 的多来源 fact 能 dedupe。
- source priority 和 fallback trace 可审计。
- Taxonomy mapping 有单元测试和 benchmark 指标。

### Phase 6：Analyst 输出与集成，Week 9-10

目标：输出可直接进入分析师模型和数据管道的文件/API。

交付项：

1. Facts JSON endpoint。
2. CSV export。
3. Excel export：
   - income statement。
   - balance sheet。
   - cashflow。
   - canonical facts。
   - validation issues。
   - risk signals。
   - source links。
4. 前端下载入口：
   - Dashboard actions。
   - Report panel actions。
5. API docs：
   - facts response sample。
   - correction response sample。
   - export columns。

验收标准：

- Excel/CSV/JSON 字段稳定。
- Export 结果包含 evidence link 或 source metadata。
- 修正后的 effective facts 能反映到 export。
- Markdown report 不再是唯一主输出。

### Phase 7：生产化、任务治理与观测，Week 10-12

目标：支撑 pilot 和稳定部署。

交付项：

1. 收敛全局 in-memory state cache：
   - 多进程 API/Celery 不应丢状态。
   - partial artifacts 显式持久化。
2. 任务治理：
   - cancel。
   - timeout cleanup。
   - retry policy visibility。
   - orphan recovery。
3. 文档级 metrics：
   - extraction engine mix。
   - pages processed。
   - tables found。
   - facts extracted。
   - correction count。
   - validation pass/fail。
   - LLM calls/tokens/cost。
   - node latency。
   - final confidence。
4. Pilot security：
   - file isolation。
   - audit log。
   - export access control。
   - secret handling。

验收标准：

- 任务失败后可定位失败阶段和 partial output。
- 页面能展示任务进度、失败原因和可恢复动作。
- Prometheus/OpenTelemetry 指标覆盖核心 pipeline。
- Pilot 用户可安全上传和导出。

### Phase 8：Pilot 闭环，Week 11-12

目标：用真实用户验证产品价值，并把失败样本变成 benchmark。

试点对象：

- 1-2 名买方/卖方分析师。
- 1 名审计/咨询用户。
- 1 名财务/数据运营用户。
- 可选 1 名量化/数据工程用户。

需要衡量：

- 每份报告节省多少建模时间。
- 哪些 facts 修正率最高。
- 哪些错误不可接受。
- 用户是否信任 evidence UI。
- 用户实际需要 Excel、CSV、JSON 还是 API。
- 部署约束：本地、私有云、Docker、API。
- 付费意愿与最小可售包装。

验收标准：

- 每个 pilot failure 都能进入 issue 或 benchmark case。
- 至少形成一份产品方向复盘。
- 决定继续深挖 Filing-to-Model，还是切向 Disclosure Review Assistant / standardized facts API。

## 6. P0 / P1 / P2 优先级

### P0：必须优先完成

- Real benchmark + eval thresholds。
- `FinancialFact` 一等公民。
- Evidence schema：page/table/row/col/bbox/quote/engine/confidence。
- Facts API。
- Human correction API 和 audit log。
- Evidence review UI。
- Excel/CSV/JSON export。
- Table extraction router 的最小版本。

### P1：有 P0 后再做

- SEC/XBRL/HTML ingestion。
- Taxonomy mapping 扩展。
- 多引擎表格 benchmark。
- Task cancellation 和 orphan recovery。
- Observability dashboard。
- Pilot security hardening。

### P2：后续增强

- 多市场财报标准化。
- Watchlist/batch processing。
- Peer comparison。
- PPT/briefing generation。
- 多 Agent critique。
- SaaS tenant、billing、quota。

## 7. 文件级实施矩阵

| 范围 | 文件 | 动作 |
| --- | --- | --- |
| Schema | `src/schemas/models.py` | 扩展 `SourceRef`、`TableCell`，新增 `FinancialFact`、`ExtractionTrace`、`Correction` |
| Fact layer | `src/finance/facts.py` | 从 statements 转 facts，应用 corrections，后续接 taxonomy |
| State | `src/agent/state.py` | 增加 facts/corrections/extraction_traces |
| Pipeline | `src/agent/nodes.py` | finalize 保存 facts，失败时保存 partial facts |
| Validation | `src/finance/validators.py` | 增加 fact-level validation、period/scale/currency checks |
| Tables | `src/pdf/tables.py` | 拆成 extractor protocol + router |
| OCR | `src/pdf/ocr.py` | 保留 OCR bbox 到 evidence，不再只拼文本 |
| Filing | `src/filings/` | 新增 SEC/HTML/XBRL ingestion |
| API | `src/api/routes.py` | facts、corrections、exports、task recovery endpoints |
| Storage | `src/storage/*` | facts/corrections/traces/export artifact 持久化 |
| Eval | `scripts/eval.py` | benchmark runner、thresholds、JSON/Markdown report |
| Metrics | `src/utils/metrics.py` | fact accuracy、evidence coverage、table metrics、cost/latency |
| Frontend API | `web/src/api/types.ts`、`web/src/api/docs.ts` | facts/corrections/export types and clients |
| Frontend UI | `web/src/views/DocumentDashboard.vue` | evidence review workspace |
| PDF Viewer | `web/src/components/PdfViewer.vue` | bbox/cell overlay highlight |
| Evidence | `web/src/components/EvidenceLink.vue` | jump + highlight + metadata tooltip |
| Statements | `web/src/components/StatementsPanel.vue` | facts table、validation state、correction actions |
| Tables | `web/src/components/TablesPanel.vue` | engine/confidence/bbox/cell review |
| Docs | `README.md`、`docs/architecture_and_capabilities.md` | 更新产品定位和能力说明 |

## 8. 关键验收命令

后端：

```bash
python -m ruff check src tests scripts
python -m mypy src --ignore-missing-imports
python -m pytest -q --timeout=60
python scripts/eval.py --output-dir data/eval-dev
```

前端：

```bash
cd web
npm run lint
npm run typecheck
npm run build
```

Docker smoke：

```bash
docker compose up --build
```

浏览器验证：

- 打开 `http://127.0.0.1:18000/ui/#/`。
- 上传 PDF。
- 等待任务完成。
- 查看 facts endpoint 是否返回数据。
- 点击 evidence 后定位到对应 PDF 页。
- 后续实现 bbox 后应高亮具体证据区域。

## 9. 风险与约束

### 9.1 准确率风险

风险：PDF 表格结构复杂、扫描件质量差、LLM 结构化输出不稳定。

缓解：优先结构化来源；引入 table router；所有 LLM 输出必须绑定 evidence；低 confidence 必须进入人工复核。

### 9.2 数据合规风险

风险：真实财报和人工标签可能包含授权或隐私约束。

缓解：真实 PDF 不入 git；benchmark 使用 manifest；必要时使用匿名标签或外部私有数据目录。

### 9.3 产品边界风险

风险：过早转向聊天、投资建议或多 Agent 展示，导致核心信任问题未解决。

缓解：P0 只围绕 facts/evidence/review/export。

### 9.4 工程复杂度风险

风险：XBRL、HTML、PDF、OCR、LLM vision 同时推进会扩大复杂度。

缓解：按 source priority 分阶段接入；每个 engine 必须经过统一 schema 和 eval。

## 10. 下一步推荐执行顺序

1. 收口 Phase 0：README/路线图正式定位为 Filing-to-Model Copilot / Financial Fact Platform，并文档化 benchmark 数据政策。
2. 完成 Phase 1 评测门槛：benchmark manifest schema、样例 manifest、threshold 配置和 eval gate。
3. 完成 correction API 和 effective facts。
4. 在前端增加 facts tab 或 review panel。
5. 给 `PdfViewer` 增加 bbox overlay。
6. 给 `EvidenceLink` 增加 row/col/bbox payload。
7. 增加 Excel/CSV/JSON export。
8. 开始 table router protocol。
9. 再接 SEC/XBRL/HTML ingestion。

这一路线的判断标准很简单：每增加一个能力，都必须让 facts 更准确、证据更可审计、复核更省时间、输出更能进入真实 analyst workflow。