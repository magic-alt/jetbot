# 贵州茅台跨项目集成案例

本案例以贵州茅台 2025 年年度报告为例，演示 jetbot 的完整 PDF 分析管线如何提取财务事实，并通过统一导出格式（schema v1.0）将数据传递给 `stock` 项目进行基本面因子分析。

| 项目 | 说明 |
|------|------|
| **公司** | 贵州茅台酒股份有限公司 (SSE: 600519.SH) |
| **文档** | 2025 年年度报告 |
| **来源** | [茅台官网](https://www.moutaichina.com/mtgf/tzzgx/gsgg/d3f80281-2.html) |
| **期间** | 截至 2025-12-31 |
| **页数** | 143 页 |

## 前置要求

```bash
pip install -e ".[dev]"
```

需要至少一个 LLM API key（脚本需要真实 LLM 来提取财务数据）：

```bash
# 方式一：DeepSeek
export DEEPSEEK_API_KEY=sk-xxx
export LLM_DEFAULT_MODEL=deepseek:deepseek-chat

# 方式二：OpenAI
export OPENAI_API_KEY=sk-xxx
export LLM_DEFAULT_MODEL=openai:gpt-4.1-mini
```

## 运行

```bash
python examples/real_pdf_analysis/run_example.py
```

使用其他财报 PDF：

```bash
python examples/real_pdf_analysis/run_example.py \
    --url https://example.com/other_report.pdf \
    --company "其他公司" \
    --ticker "000001.SZ" \
    --period-end 2025-12-31 \
    --language zh
```

## 输出

运行成功后目录结构如下：

```
examples/real_pdf_analysis/
├── fixtures/moutai_2025_annual.pdf           # 缓存的 PDF 下载
└── output/<doc_id>/
    ├── raw.pdf
    ├── meta.json
    ├── extracted/
    │   ├── pages.json
    │   ├── tables.json
    │   ├── statements.json
    │   ├── facts.json
    │   ├── notes.json
    │   └── risk_signals.json
    └── report/
        ├── trader_report.json
        └── trader_report.md
```

脚本还会自动导出 schema v1.0 格式的 JSON 文件，包含 5 个核心财务指标：

| 指标 | 含义 | 计算方式 |
|------|------|----------|
| `revenue_growth` | 营收增长率 | (本期 - 上期) / \|上期\| |
| `net_profit_growth` | 净利润增长率 | (本期 - 上期) / \|上期\| |
| `gross_margin` | 毛利率 | 毛利润 / 营收 |
| `operating_cash_flow` | 经营现金流 | 经营活动现金流量净额 |
| `debt_ratio` | 资产负债率 | 负债合计 / 资产总计 |

## 跨项目集成（stock）

如果 `stock` 项目与 `jetbot` 位于同级目录，脚本会自动将导出 JSON 复制到 `stock/jetbot_exports/` 并运行 `FundamentalFilter` 进行基本面筛选演示。

## 茅台 2025 年参考数据

基于真实年报提取的 5 个核心指标：

| 指标 | 值 | 说明 |
|------|-----|------|
| 营收增长率 | -1.21% | 营收 1688.4 亿，同比微降 |
| 净利润增长率 | -4.53% | 净利润 823.2 亿，小幅下滑 |
| 毛利率 | 91.18% | 极高毛利，符合白酒行业特征 |
| 经营现金流 | 615.2 亿元 | 同比下降 33.5% |
| 资产负债率 | 16.33% | 极低杠杆 |

### 风险信号

jetbot 从年报中识别出的关键风险：

1. **经营现金流大幅下降**（高）：同比降 33.46%，与净利润降幅（-4.53%）显著背离
2. **利润率承压**（低）：营收降 1.21% 但净利润降 4.53%
3. **高分红**（低）：拟分红 350.3 亿元，派息率 42.56%

## 数据流架构

```
┌─────────────────────────────────────────┐
│  jetbot (PDF → 财务事实)                │
│                                         │
│  moutai_2025_annual.pdf                 │
│      ↓ analyze pipeline (11 nodes)      │
│  extracted/statements.json              │
│      ↓ export-facts command             │
│  moutai_2025_export.json (schema v1.0)  │
└──────────────┬──────────────────────────┘
               │  JSON file / API endpoint
               ▼
┌─────────────────────────────────────────┐
│  stock (基本面因子 → 策略过滤)           │
│                                         │
│  JetbotFactsProvider.load()             │
│      ↓ get_metrics_dict()               │
│  FundamentalFilter.score_symbol()       │
│      ↓ filter_passed()                  │
│  FundamentalFilterStrategy (backtrader)  │
└─────────────────────────────────────────┘
```

## 免责声明

- 下载的 PDF 为公开发布的投资者关系材料，不由本仓库重新分发
- 输出结果仅供参考，不构成投资建议
