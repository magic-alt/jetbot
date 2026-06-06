# Jetbot 全面技术审查与下一阶段规划

**审查日期**: 2026-06-07  
**审查范围**: 全量源码（src/ 40+ 文件）、测试套件（tests/ 35+ 文件）、Web 前端（web/）、CI/CD、文档、Git 历史  
**当前状态**: P1-P7 升级计划全部完成，319 测试通过，10 节点 LangGraph pipeline，FastAPI + CLI + Vue 3 Dashboard

---

## 一、项目现状评估

### 1.1 架构成熟度（3.8/5）

项目的模块化设计清晰，10 个核心模块（agent/api/llm/finance/pdf/storage/market/utils/export/schemas/cli）之间职责边界合理。Protocol-based 抽象（StorageBackend, PdfEngine, LLMClient, MarketDataProvider, OCREngine）实现了良好的依赖倒置。几乎每个外部依赖都有优雅降级方案（MockLLM, LocalStore, DummyMarketData, Token-overlap RAG, Tesseract fallback），这使得项目在最小依赖下即可运行。

Pydantic v2 的 `extra="forbid"` 策略在所有 schema 上统一执行，结构化日志、Prometheus metrics、OpenTelemetry tracing 三位一体的可观测性体系已经就位。

### 1.2 代码卫生（4/5）

ruff 检查全绿（F401/F811 零告警），无 TODO/FIXME/HACK 标记积累。历史优化报告记录的 35 个问题已全部修复。提交信息遵循 conventional commits 格式，PR 工作流和分支保护规则执行严格。

### 1.3 核心短板

审查发现的主要短板集中在四个方面：并发安全性（全局可变状态缺乏保护）、异常处理（多处 `except Exception: pass` 吞掉错误）、巨型文件（nodes.py 超 1400 行）、以及文档与代码的漂移。

---

## 二、技术债清单（按优先级排序）

### P0 -- 安全与数据完整性（立即修复）

| # | 问题 | 文件与行号 | 修复方案 | 工作量 |
|---|------|-----------|---------|--------|
| 1 | `LocalStore._safe_path` 路径遍历检查用 `startswith` 可被绕过 | `src/storage/local_store.py:32` | 改用 `resolved.is_relative_to(self.base_dir)` | 0.5h |
| 2 | `LocalStore.save_json` 未调用 `_safe_path` 验证路径 | `src/storage/local_store.py:94-99` | 添加 `_safe_path` 调用 | 0.5h |
| 3 | API 认证默认禁用，无生产环境强制机制 | `src/api/auth.py:27-28` | `ENV=production` 时强制要求 `API_KEYS` | 1h |
| 4 | CORS 默认 `"*"` 允许所有来源 | `src/api/main.py:29` | 生产环境默认空列表 | 0.5h |
| 5 | `_save_partial_results` 用 `model_dump()` 而非 `model_dump(mode="json")` | `src/api/routes.py:680-698` | 统一序列化模式 | 0.5h |
| 6 | Golden 测试断言 `assert accuracy >= 0.0` 永远不失败 | `tests/golden/test_golden.py` 多处 | 设置有意义的最小阈值（如 `>= 0.6`） | 1h |
| 7 | CI 流水线不运行前端单元测试 | `.github/workflows/ci.yml` | `web-build` job 增加 `npm run test:unit` | 0.5h |

### P1 -- 可靠性与稳定性（本迭代内修复）

| # | 问题 | 文件与行号 | 修复方案 | 工作量 |
|---|------|-----------|---------|--------|
| 8 | `_state_cache` 无并发保护，多文档并发分析会竞态 | `src/agent/graph.py:27` | 添加 `threading.Lock` 或改为 per-request cache | 2h |
| 9 | `_wrap()` 每次创建/销毁 `ThreadPoolExecutor` | `src/agent/graph.py:105` | 使用全局共享 executor + `Future` | 2h |
| 10 | `_call_llm_parallel_structured` 吞掉所有异常 | `src/agent/nodes.py:1229` | 记录 `logger.warning("LLM parallel call failed", exc_info=True)` | 0.5h |
| 11 | `_save_partial_results` 中 `except Exception: pass` | `src/api/routes.py:699-700` | 记录 warning 日志 | 0.5h |
| 12 | PgStore 多处 `except Exception: pass` | `src/storage/pg_store.py` 多处 | 记录 warning 日志 + 异常类型 | 1h |
| 13 | Anthropic client `max_tokens=4096` 硬编码 | `src/llm/anthropic_client.py:48` | 环境变量 `LLM_MAX_OUTPUT_TOKENS` | 0.5h |
| 14 | Rate limiter `_windows` dict 内存无限增长 | `src/api/main.py:76-93` | 添加定期清理或带 TTL 的 LRU | 1h |
| 15 | Dockerfile 使用 `pip install -e .`（可编辑模式） | `Dockerfile` | 改为 `pip install .` | 0.5h |

### P2 -- 代码质量与可维护性（下一迭代）

| # | 问题 | 文件与行号 | 修复方案 | 工作量 |
|---|------|-----------|---------|--------|
| 16 | **`nodes.py` 超 1400 行，承担全部 pipeline 节点逻辑** | `src/agent/nodes.py` | 拆分为 `ingest_nodes.py`, `extraction_nodes.py`, `analysis_nodes.py`, `report_nodes.py` | 8h |
| 17 | `_parse_fallback` / `_render_user_prompt` 在两个 LLM client 中重复 | `openai_client.py` + `anthropic_client.py` | 抽取到 `src/llm/utils.py` | 2h |
| 18 | 多处 `type: ignore[arg-type]` 压制 str -> Literal 类型错误 | `src/agent/nodes.py` | 在赋值处添加 `Literal` 类型断言或 `cast()` | 1h |
| 19 | 硬编码货币单位 `"USD millions"` | `src/agent/nodes.py:835` | 从 `doc_meta.language` 推断货币 | 1h |
| 20 | `_detect_statement_type` 关键词硬编码 | `src/agent/nodes.py:692-718` | 提取到 `src/finance/constants.py` | 1h |
| 21 | `export/builder.py` 中 `if rev_cur` falsy 检查（revenue=0 合法） | `src/export/builder.py:135,152,168,175,209` | 改为 `if rev_cur is not None` | 1h |
| 22 | 重试次数/退避策略全部硬编码 | `nodes.py` 多处 | 统一为 `RetryConfig` 类 | 2h |
| 23 | PgStore 条件类定义（`DocumentRecord is not None` 检查散落各处） | `src/storage/pg_store.py` | 使用始终定义的 stub 类替代 | 2h |
| 24 | `schemas/__init__.py` 缺少 12 个模型导出，包括核心的 `FinancialFact` | `src/schemas/__init__.py` | 补充 `__all__` 列表 | 0.5h |

### P3 -- 性能优化

| # | 问题 | 文件与行号 | 修复方案 | 工作量 |
|---|------|-----------|---------|--------|
| 25 | `_read_rate_limits` 每次请求重新解析环境变量 | `src/api/main.py:111` | `functools.lru_cache` | 0.5h |
| 26 | `_get_allowed_keys` 每次请求重新解析 `API_KEYS` | `src/api/auth.py:9-15` | 缓存结果 | 0.5h |
| 27 | `build_rag_index` 在 `context.py` 中与 `nodes.py` 重复构建 | `src/agent/context.py:130` | 统一索引生命周期管理 | 2h |
| 28 | `get_pdf_engine` 每次创建新实例 | `src/pdf/engine.py:280` | 添加实例缓存 | 0.5h |
| 29 | `NODE_TIMEOUT_S` 每次节点调用重新读取 `os.getenv` | `src/agent/graph.py:103` | 模块级缓存 | 0.5h |

### P4 -- 测试覆盖盲点

| 模块 | 盲点 | 风险 |
|------|------|------|
| `src/llm/` | 整个模块仅 1 个测试文件，provider 路由/超时/重试/降级逻辑未覆盖 | **高** |
| `src/agent/adapters/hermes.py` | 外部集成点零测试覆盖 | **高** |
| `src/agent/graph.py` | 并发文档处理下 `_state_cache` 竞态条件 | 中 |
| `src/agent/nodes.py` | `_parse_number` 边界值；`_split_long_paragraph` 无标点文本 | 中 |
| `src/llm/openai_client.py` | Responses API -> Chat Completions fallback 路径 | 中 |
| `src/export/builder.py` | 五个核心指标均无法计算时的空 envelope；revenue=0 行为 | 中 |
| `src/storage/local_store.py` | 路径遍历攻击变体 | 中 |
| `src/market/event_study.py` | 小样本窗口 t-test 准确性 | 低 |

### P5 -- 文档与代码卫生

| # | 问题 | 修复方案 | 工作量 |
|---|------|---------|--------|
| 30 | README 引用已删除的 `examples/real_pdf_analysis/` | 更新为新示例路径 | 0.5h |
| 31 | AGENTS.md 写 Python 3.11+，实际要求 3.12+ | 更正版本号 | 5min |
| 32 | `src/agent/adapters/` 在架构文档中无记录 | 补充 Hermes adapter 说明 | 1h |
| 33 | architecture 文档声称使用 slowapi，实际为自研 RateLimiter | 更正描述 | 0.5h |
| 34 | `uv.lock` 未纳入版本控制 | `git add uv.lock` | 5min |
| 35 | 2 个已合并本地分支未清理 | `git branch -d` | 5min |
| 36 | PROJECT.md 进度表显示 P5-P7 待实施，实际已完成 | 更新进度表 | 0.5h |
| 37 | `AnalysisFinding` 类已定义但全代码库无引用 | 确认为预留接口或删除 | 0.5h |
| 38 | `yfinance` 未在 `pyproject.toml` 的 `[market]` extra 中声明 | 添加依赖声明 | 5min |

---

## 三、功能闭环规划

### 3.1 路线图 Phase 4-8 待实施清单

根据 `docs/financial_fact_platform_roadmap.md` 定义的 90 天路线图，Phase 0-3 已完成，以下为剩余阶段的闭环规划：

**Phase 4 -- 表格多引擎 Router（预估 3 天）**

当前 `src/pdf/tables.py` 仅使用 pdfplumber 单一引擎。需要实现表格提取 Protocol + Router 模式，支持 pdfplumber / camelot / 未来引擎的插拔，根据表格类型（有边框/无边框/跨页）自动选择引擎，并合并跨页表格。

**Phase 5 -- SEC/XBRL/HTML Ingestion（预估 5-7 天）**

当前仅支持 PDF 输入。需要新增 `src/filings/` 模块，支持 SEC EDGAR XBRL 解析、HTML 年报提取（港股/A股 HTML 披露）、以及统一的 IngestionRouter 根据输入格式自动分发。

**Phase 6 -- Analyst 输出集成（预估 3-4 天）**

当前 export 模块仅支持 JSON envelope。需要补充 Excel（openpyxl）和 CSV 导出，实现 Analyst-ready 输出（含格式化财务报表、关键指标图表、evidence 超链接）。

**Phase 7 -- 生产化任务治理（预估 3-4 天）**

当前任务管理基于 SQLite TaskStore，缺少 orphan recovery（崩溃任务恢复）、task cancellation（用户主动取消）、task timeout enforcement（强制超时终止）、以及任务级别的资源隔离。

**Phase 8 -- Pilot 闭环（预估 2-3 天）**

建立 pilot 用户反馈机制，包括 extraction 质量打分 UI、correction 统计仪表盘、常见错误模式自动识别、以及 A/B 测试框架（不同 prompt/模型版本对比）。

### 3.2 建议的执行顺序

基于"先稳定基础，再扩展能力"的原则，建议按以下顺序执行：

**Sprint 1（1 周）-- 技术债清理 + 安全加固**

集中处理 P0 全部 7 项 + P1 的 8 项，确保安全和可靠性基线。同时修复 P5 中的文档问题（30-36）。预计总工作量约 25-30 人时。交付标准：所有 P0/P1 项修复完成，测试数量从 319 增长到 340+。

**Sprint 2（1 周）-- 代码重构 + 测试补全**

执行 P2 中的 `nodes.py` 拆分（#16，最大单项重构），LLM utils 抽取（#17），重试策略统一（#22）。同时补充 P4 中的 LLM 测试和 Hermes adapter 测试。执行 P3 全部性能优化。预计总工作量约 30-35 人时。交付标准：nodes.py 拆分为 4 个子模块，每个不超过 400 行；LLM 层测试覆盖达到 70%+。

**Sprint 3（1-2 周）-- Phase 4 表格 Router + Phase 6 Export 闭环**

实现表格多引擎 Router 和 Excel/CSV 导出。这两个功能直接提升产品的输出质量和使用场景覆盖面。交付标准：camelot 引擎可用，跨页表格合并工作；Excel 导出含格式化报表。

**Sprint 4（2 周）-- Phase 5 多格式 Ingestion**

实现 SEC/XBRL/HTML 输入支持。这是扩大用户基础（从 PDF-only 到多格式）的关键步骤。交付标准：SEC EDGAR 10-K XBRL 文件可解析；HTML 年报可提取。

**Sprint 5（1-2 周）-- Phase 7 任务治理 + Phase 8 Pilot 闭环**

实现生产化任务管理和 pilot 反馈机制。交付标准：orphan recovery 工作，任务可取消，pilot 质量打分 UI 可用。

---

## 四、关键决策点

在开始执行前，有几个架构决策需要明确：

**决策 1：nodes.py 的拆分策略**

方案 A -- 按 pipeline 阶段拆分（ingest / extract / analyze / report），每个文件 300-400 行，职责最清晰。方案 B -- 按关注点拆分（llm_interaction / data_processing / validation），更利于复用但可能跨 pipeline 阶段。建议采用方案 A，因为 LangGraph 的节点本身就是按阶段组织的。

**决策 2：表格 Router 的默认引擎选择**

方案 A -- pdfplumber 为默认，camelot 为可选增强（当前架构的自然延伸）。方案 B -- 双引擎并行提取后合并（更高准确度但更慢）。建议采用方案 A，与现有的可选依赖组设计一致。

**决策 3：Export 模块的 Excel 库选择**

方案 A -- openpyxl（纯 Python，无 C 依赖，Docker 友好）。方案 B -- xlsxwriter（更快，功能更丰富，但只写不读）。建议采用方案 A，因为 export 场景需要模板填充能力（读+写）。

---

## 五、量化目标

| 指标 | 当前值 | Sprint 1 目标 | Sprint 2 目标 | 全部完成目标 |
|------|--------|--------------|--------------|------------|
| 测试数量 | 319 | 340+ | 380+ | 450+ |
| 最大单文件行数 | 1433（nodes.py） | 1433 | <400 | <400 |
| LLM 层测试覆盖 | ~15% | ~15% | 70%+ | 85%+ |
| `except Exception: pass` 次数 | 5+ | 0 | 0 | 0 |
| 文档与代码不一致项 | 8 | 0 | 0 | 0 |
| Golden 测试有效阈值 | 0/5 case | 5/5 case | 5/5 case | 10+ case |
| Export 格式 | JSON | JSON | JSON | JSON+Excel+CSV |
| 输入格式 | PDF | PDF | PDF | PDF+XBRL+HTML |

---

## 六、风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| nodes.py 拆分引入回归 bug | 中 | 高 | 拆分前后运行全量测试对比；保持函数签名不变 |
| langchain 生态升级引入 breaking change | 中 | 中 | Sprint 2 中锁定版本上限（`~=0.3`） |
| 表格多引擎合并逻辑复杂度超预期 | 中 | 中 | Phase 4 先支持"最佳引擎选择"而非"合并" |
| XBRL 解析的 schema 复杂度 | 高 | 中 | 先支持 SEC EDGAR 标准 taxonomy，自定义 taxonomy 延后 |
| Sprint 间依赖导致阻塞 | 低 | 中 | P0-P2 之间无强依赖，可并行推进 |

---

*文档生成时间: 2026-06-07 | 审查工具: QoderWork*
