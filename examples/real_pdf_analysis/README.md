# Real-PDF analysis example

This example runs the full jetbot pipeline against a **real, public listed-company
financial report PDF**. By default it downloads:

- **Company:** Apple Inc. (NASDAQ: AAPL)
- **Document:** FY2024 Q4 Consolidated Financial Statements
- **Source:** <https://www.apple.com/newsroom/pdfs/fy2024-q4/FY24_Q4_Consolidated_Financial_Statements.pdf>
- **Period end:** 2024-09-28
- **License:** Public investor-relations material published by Apple.

No API key is required — the example forces the deterministic mock LLM
(`LLM_DEFAULT_MODEL=mock:mock`), so it is reproducible offline after the
initial download.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## Run

```bash
python examples/real_pdf_analysis/run_example.py
```

Use a different filing:

```bash
python examples/real_pdf_analysis/run_example.py \
    --url https://www.berkshirehathaway.com/qtrly/3rdqtr24.pdf \
    --company "Berkshire Hathaway Inc." \
    --period-end 2024-09-30 \
    --report-type quarterly
```

## Output

After a successful run you will find:

```
examples/real_pdf_analysis/
├── fixtures/FY24_Q4_Consolidated_Financial_Statements.pdf   # cached download
└── output/<doc_id>/
    ├── raw.pdf
    ├── meta.json
    ├── extracted/
    │   ├── pages.json
    │   ├── tables.json
    │   ├── statements.json
    │   ├── notes.json
    │   └── risk_signals.json
    └── report/
        ├── trader_report.json
        └── trader_report.md
```

The script also prints the first 30 lines of `trader_report.md` to stdout
so you can confirm the pipeline produced a report.

## Switching to a real LLM

Unset the mock override and point the agent at OpenAI or Anthropic:

```bash
export OPENAI_API_KEY=sk-...
export LLM_DEFAULT_MODEL=openai:gpt-4.1-mini
python examples/real_pdf_analysis/run_example.py
```

## Notes & disclaimers

- The downloaded PDF is **not** redistributed by this repository; the script
  fetches it from the original publisher each run (or reuses the local cache
  under `fixtures/`).
- Outputs are illustrative only. They are produced by the mock LLM unless you
  configure a real provider. They are **not** investment advice.
