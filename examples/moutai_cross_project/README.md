# 贵州茅台跨项目集成案例

本案例演示 jetbot 的完整 PDF 分析管线如何提取财务事实，并通过统一导出格式（schema v1.0）将数据传递给 `stock` 项目进行基本面因子分析。

## 案例概览

| 项目 | 说明 |
|------|------|
| **公司** | 贵州茅台酒股份有限公司 (SSE: 600519.SH) |
| **文档** | 2025 年年度报告 |
| **来源** | [茅台官网](https://www.moutaichina.com/mtgf/tzzgx/gsgg/d3f80281-2.html) |
| **期间** | 截至 2025-12-31 |
| **页数** | 143 页 |

## 前置要求

```bash
# 安装 jetbot 及其依赖
pip install -e ".[dev]"

# 配置 LLM（需要至少一个 API key）
# 方式一：DeepSeek
export DEEPSEEK_API_KEY=sk-xxx
export LLM_DEFAULT_MODEL=deepseek:deepseek-chat

# 方式二：OpenAI
export OPENAI_API_KEY=sk-xxx
export LLM_DEFAULT_MODEL=openai:gpt-4.1-mini
```

## 步骤一：下载财报 PDF

```bash
curl -L -o moutai_2025_annual.pdf \
  "https://www.moutaichina.com/mtgf/articleFileDir/2026-04/17/07cf01cc11a14ea18cfadf9ebe2a4eb3.pdf"
```

## 步骤二：运行 jetbot 分析

```bash
python -m src.cli analyze \
  --pdf moutai_2025_annual.pdf \
  --company "贵州茅台" \
  --ticker "600519.SH" \
  --filing-type "annual" \
  --period-end "2025-12-31" \
  --language "zh" \
  --out data
```

分析管线依次执行 11 个 LangGraph 节点：PDF 文本提取 → 表格识别 → 章节分块 → 财务报表提取 → 校验调和 → 关键附注提取 → 风险信号生成 → 分析上下文构建 → 深度分析 → 交易报告生成 → 事件研究。

## 步骤三：导出统一格式 JSON

```bash
python -m src.cli export-facts <doc_id> --out data --output moutai_2025_export.json
```

导出模块从提取的财务报表自动计算 5 个核心指标：

| 指标 | 含义 | 计算方式 |
|------|------|----------|
| `revenue_growth` | 营收增长率 | (本期营收 - 上期营收) / \|上期营收\| |
| `net_profit_growth` | 净利润增长率 | (本期净利润 - 上期净利润) / \|上期净利润\| |
| `gross_margin` | 毛利率 | 毛利润 / 营收 |
| `operating_cash_flow` | 经营现金流 | 经营活动现金流量净额 |
| `debt_ratio` | 资产负债率 | 负债合计 / 资产总计 |

## 步骤四：导入 stock 进行基本面分析

```bash
# 在 stock 项目目录中
mkdir -p jetbot_exports
cp /path/to/moutai_2025_export.json jetbot_exports/

python -c "
from src.data_sources.jetbot_facts import JetbotFactsProvider
from src.strategies.fundamental_filter import FundamentalFilter, FundamentalThresholds

provider = JetbotFactsProvider(export_dir='jetbot_exports')
filt = FundamentalFilter(provider)
result = filt.score_symbol('600519.SH')
print(result.summary())
for m, d in result.details.items():
    print(f'  {m}: {d}')
"
```

## 茅台 2025 年分析结果

基于本案例的导出 JSON，5 个核心指标如下：

| 指标 | 值 | 说明 |
|------|-----|------|
| 营收增长率 | -1.21% | 营收 1688.4 亿，同比微降 |
| 净利润增长率 | -4.53% | 净利润 823.2 亿，小幅下滑 |
| 毛利率 | 91.18% | 营收 1688.4 亿 - 成本 148.9 亿，极高毛利 |
| 经营现金流 | 615.2 亿元 | 同比下降 33.5%，主要受财务子公司存款变动影响 |
| 资产负债率 | 16.33% | 负债 496.1 亿 / 资产 3038.3 亿，极低杠杆 |

### 关键风险信号

jetbot 从年报中识别出以下风险信号：

1. **经营现金流大幅下降**（高严重度）：经营现金流同比降 33.46%，而净利润仅降 4.53%，两者背离显著。公司解释为财务子公司成员存款减少。
2. **营收与净利润下降幅度不一致**（低严重度）：营收降 1.21% 但净利润降 4.53%，暗示利润率承压。
3. **高分红**（低严重度）：拟分红 350.3 亿元，派息率 42.56%，在现金流下降年份值得关注。

### 默认过滤结果

使用 `stock` 项目的 `FundamentalFilter` 默认阈值（要求增长率为正）：

- 评分：**0.99**（非常高）
- 结果：**FAIL** — 营收增长率（-1.21%）和净利润增长率（-4.53%）为负，低于 `min=0.0` 阈值

这是逻辑正确的行为。茅台基本面极强（毛利率 91%、负债率仅 16%、现金流充裕），但 2025 年出现了营收和利润的双降。如需将其纳入选股池，可调整阈值：

```python
# 放宽增长要求，更看重绝对质量
thresholds = FundamentalThresholds(
    revenue_growth_min=-0.05,    # 允许 5% 以内的下滑
    net_profit_growth_min=-0.10, # 允许 10% 以内的下滑
    gross_margin_min=0.30,
    debt_ratio_max=0.70,
)
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `moutai_2025_export.json` | 导出的统一格式 JSON（schema v1.0），可直接被 stock 消费 |
| `run_example.py` | 端到端运行脚本（含 PDF 下载、分析、导出、stock 导入） |
| `.gitignore` | 忽略大型 PDF 和生成的数据文件 |

## 跨项目数据流架构

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
