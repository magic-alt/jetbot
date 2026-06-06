# 泡泡玛特跨项目集成案例

本案例以泡泡玛特国际集团 2024 年度业绩报告为例，演示 jetbot 的完整 PDF 分析管线如何提取财务事实，并通过统一导出格式（schema v1.0）将数据传递给 `stock` 项目进行基本面因子分析。

## 案例概览

| 项目 | 说明 |
|------|------|
| **公司** | 泡泡玛特国际集团有限公司 (HKEX: 9992.HK) |
| **文档** | 2024 年度业绩公告 |
| **来源** | [HKEXnews](https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=zh) (搜索 9992) |
| **期间** | 截至 2024-12-31 |
| **语言** | 中文 |

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

## 运行

```bash
python examples/popmart_annual_analysis/run_example.py
```

使用其他财报 PDF：

```bash
python examples/popmart_annual_analysis/run_example.py \
    --url https://example.com/other_report.pdf \
    --company "其他公司" \
    --ticker "000001.HK" \
    --period-end 2024-12-31 \
    --language zh
```

## 步骤说明

### 步骤一：下载财报 PDF

脚本从 HKEXnews 下载泡泡玛特 2024 年度业绩公告（或使用用户提供的 URL）。PDF 会缓存到本地，后续运行跳过下载。

### 步骤二：运行 jetbot 分析管线

```bash
python -m src.cli analyze \
  --pdf popmart_2024_annual.pdf \
  --company "泡泡玛特" \
  --ticker "9992.HK" \
  --filing-type annual \
  --period-end 2024-12-31 \
  --language zh \
  --out data
```

分析管线依次执行 11 个 LangGraph 节点：PDF 文本提取 → 表格识别 → 章节分块 → 财务报表提取 → 校验调和 → 关键附注提取 → 风险信号生成 → 分析上下文构建 → 深度分析 → 交易报告生成 → 事件研究。

### 步骤三：导出统一格式 JSON

```bash
python -m src.cli export-facts <doc_id> --out data --output popmart_2024_export.json
```

导出模块从提取的财务报表自动计算 5 个核心指标：

| 指标 | 含义 | 计算方式 |
|------|------|----------|
| `revenue_growth` | 营收增长率 | (本期营收 - 上期营收) / \|上期营收\| |
| `net_profit_growth` | 净利润增长率 | (本期净利润 - 上期净利润) / \|上期净利润\| |
| `gross_margin` | 毛利率 | 毛利润 / 营收 |
| `operating_cash_flow` | 经营现金流 | 经营活动现金流量净额 |
| `debt_ratio` | 资产负债率 | 负债合计 / 资产总计 |

### 步骤四（可选）：导入 stock 进行基本面分析

如果 `stock` 项目与 `jetbot` 位于同级目录，脚本会自动将导出 JSON 复制到 `stock/jetbot_exports/` 并运行 `FundamentalFilter` 进行基本面筛选演示。

## 泡泡玛特 2024 年分析结果

基于本案例的导出 JSON，5 个核心指标如下：

| 指标 | 值 | 说明 |
|------|-----|------|
| 营收增长率 | +106.9% | 营收 130.38 亿元，2023 年 63.01 亿元，翻倍增长 |
| 净利润增长率 | +185.7% | 归母净利 34.0 亿，2023 年 11.9 亿，爆发式增长 |
| 毛利率 | 66.8% | 营收 130.38 亿 - 成本 43.29 亿，潮玩行业高毛利 |
| 经营现金流 | 84.76 亿元 | 现金转化率极高（OCF / 净利润 = 2.5x） |
| 资产负债率 | 26.8% | 负债 39.86 亿 / 资产 148.71 亿，极低杠杆 |

### 关键风险信号

jetbot 从业绩公告中识别出以下风险信号：

1. **海外营收占比快速提升**（中严重度）：海外收入占比从 2023 年的约 15% 跃升至 2024 年的 30%+，地理扩张带来汇率、合规及供应链风险。
2. **IP 集中度风险**（中严重度）：头部 IP（Molly、SKULLPANDA、Labubu 等）贡献了大部分收入，单一 IP 热度下降可能对业绩产生较大波动。
3. **估值与增长可持续性**（低严重度）：当前估值隐含了高增长预期，需关注潮玩行业竞争加剧及消费者偏好变化的影响。

### 默认过滤结果

使用 `stock` 项目的 `FundamentalFilter` 默认阈值（要求增长率为正）：

- 评分：**1.00**（满分）
- 结果：**PASS** — 所有 5 项指标均满足默认阈值

泡泡玛特 2024 年的基本面表现极为突出：营收翻倍增长、净利率超 25%、毛利率 66.8%、现金流远超净利润、负债率仅 26.8%。在默认阈值下获得满分并通过筛选，是典型的高成长 + 高质量基本面案例。

## 文件说明

| 文件 | 说明 |
|------|------|
| `popmart_2024_export.json` | 导出的统一格式 JSON（schema v1.0），可直接被 stock 消费 |
| `run_example.py` | 端到端运行脚本（含 PDF 下载、分析、导出、stock 导入） |
| `.gitignore` | 忽略大型 PDF 和生成的数据文件 |

## 跨项目数据流架构

```
+------------------------------------------+
|  jetbot (PDF -> 财务事实)                |
|                                          |
|  popmart_2024_annual.pdf                 |
|      |  analyze pipeline (11 nodes)      |
|      v                                   |
|  extracted/statements.json               |
|      |  export-facts command             |
|      v                                   |
|  popmart_2024_export.json (schema v1.0)  |
+-----------------+------------------------+
                  |  JSON file / API endpoint
                  v
+------------------------------------------+
|  stock (基本面因子 -> 策略过滤)           |
|                                          |
|  JetbotFactsProvider.load()              |
|      |  get_metrics_dict()               |
|      v                                   |
|  FundamentalFilter.score_symbol()        |
|      |  filter_passed()                  |
|      v                                   |
|  FundamentalFilterStrategy (backtrader)   |
+------------------------------------------+
```

## 免责声明

- 下载的 PDF 为公开发布的投资者关系材料，不由本仓库重新分发
- 输出结果仅供参考，不构成投资建议
