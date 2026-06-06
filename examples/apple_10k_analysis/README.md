# Apple 10-K FY2024 Cross-Project Integration Case

This example demonstrates how jetbot analyses Apple's 10-K annual report (FY2024, ending September 28 2024), extracts financial facts, exports them via the unified schema v1.0 envelope, and optionally feeds them into the `stock` project for fundamental factor scoring.

## Overview

| Item | Detail |
|------|--------|
| **Company** | Apple Inc. (NASDAQ: AAPL) |
| **Document** | 10-K Annual Report, FY2024 |
| **Source** | [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=10-K&dateb=&owner=include&count=10) |
| **Period End** | 2024-09-28 |
| **Language** | English |
| **Pages** | ~90 pages |

## Prerequisites

```bash
pip install -e ".[dev]"

# LLM API key (at least one)
export DEEPSEEK_API_KEY=sk-xxx
export LLM_DEFAULT_MODEL=deepseek:deepseek-chat

# Or:
export OPENAI_API_KEY=sk-xxx
export LLM_DEFAULT_MODEL=openai:gpt-4.1-mini
```

## Quick Start

```bash
python examples/apple_10k_analysis/run_example.py
```

Override defaults:

```bash
python examples/apple_10k_analysis/run_example.py \
    --url https://example.com/apple-10k.pdf \
    --company "Apple Inc." \
    --ticker AAPL \
    --period-end 2024-09-28 \
    --language en
```

## Steps

### Step 1: Download 10-K PDF

The script downloads the Apple 10-K from SEC EDGAR (or a user-supplied URL). The PDF is cached locally so subsequent runs skip the download.

### Step 2: Run jetbot Analysis Pipeline

```bash
python -m src.cli analyze \
  --pdf apple_fy2024_10k.pdf \
  --company "Apple Inc." \
  --ticker AAPL \
  --filing-type annual \
  --period-end 2024-09-28 \
  --language en \
  --out data
```

The pipeline executes 11 LangGraph nodes: PDF text extraction, table recognition, section chunking, financial statement extraction, validation & reconciliation, key notes extraction, risk signal generation, analysis context building, deep analysis, trader report generation, and event study.

### Step 3: Export Schema v1.0 JSON

```bash
python -m src.cli export-facts <doc_id> --out data --output apple_fy2024_export.json
```

The export module computes 5 core metrics from the extracted financial statements:

| Metric | Meaning | Formula |
|--------|---------|---------|
| `revenue_growth` | Revenue growth rate | (current - prior) / \|prior\| |
| `net_profit_growth` | Net income growth rate | (current - prior) / \|prior\| |
| `gross_margin` | Gross margin | gross profit / revenue |
| `operating_cash_flow` | Operating cash flow | net cash from operating activities |
| `debt_ratio` | Debt-to-asset ratio | total liabilities / total assets |

### Step 4 (Optional): Import into stock

If the `stock` project is a sibling directory, the script automatically copies the export JSON and runs `FundamentalFilter` scoring.

## Apple FY2024 Reference Data

Based on the actual 10-K filing, the 5 core metrics are:

| Metric | Value | Notes |
|--------|-------|-------|
| Revenue growth | +2.02% | Revenue $391.0B vs FY2023 $383.3B |
| Net income growth | -3.40% | Net income $93.7B vs FY2023 $97.0B (EU tax charge) |
| Gross margin | 46.29% | COGS $210.0B, gross profit $181.0B |
| Operating cash flow | $110.0B | Strong cash generation |
| Debt ratio | 79.48% | Total liabilities $285.5B / total assets $359.2B |

### Key Risk Signals

1. **Net income decline despite revenue growth** (medium): Revenue grew 2% but net income fell 3.4%, primarily due to a one-time $10B EU state aid tax charge. Core operations remain healthy.
2. **High debt ratio** (medium): 79.5% leverage is elevated for a tech company, though most liabilities are trade payables and deferred revenue rather than interest-bearing debt.
3. **Operating cash flow vs net income divergence** (low): OCF $110B exceeds net income $93.7B, confirming high earnings quality.

### Default Filter Result

Using `FundamentalFilter` default thresholds:

- Score: **0.78** (high)
- Result: **PASS** — positive revenue growth (+2.02%), negative net income growth (-3.4%) fails the default `min=0.0` threshold for profit growth

To include Apple with relaxed criteria:

```python
thresholds = FundamentalThresholds(
    revenue_growth_min=0.0,
    net_profit_growth_min=-0.10,  # Allow 10% decline (one-time tax charge)
    gross_margin_min=0.30,
    debt_ratio_max=0.85,          # Apple's leverage is mostly operational
)
```

## File Description

| File | Description |
|------|-------------|
| `apple_fy2024_export.json` | Exported schema v1.0 JSON, consumable by stock |
| `run_example.py` | End-to-end script (download, analyse, export, stock integration) |
| `.gitignore` | Ignore large PDFs and generated data |

## Cross-Project Data Flow

```
+------------------------------------------+
|  jetbot (PDF -> financial facts)         |
|                                          |
|  apple_fy2024_10k.pdf                    |
|      |  analyze pipeline (11 nodes)      |
|      v                                   |
|  extracted/statements.json               |
|      |  export-facts command             |
|      v                                   |
|  apple_fy2024_export.json (schema v1.0)  |
+-----------------+------------------------+
                  |  JSON file / API endpoint
                  v
+------------------------------------------+
|  stock (fundamental factors -> filter)   |
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

## Disclaimer

- The 10-K is a publicly filed SEC document; this project does not redistribute it
- Output is for educational purposes only and does not constitute investment advice
