"""End-to-end example: Moutai 2025 annual report → jetbot analysis → stock import.

Downloads the Guizhou Moutai 2025 annual report PDF, runs the full jetbot
analysis pipeline, exports normalised financial facts (schema v1.0), and
optionally imports them into the ``stock`` project for fundamental filtering.

Usage
-----
    python examples/moutai_cross_project/run_example.py

Requires at least one LLM provider key (DEEPSEEK_API_KEY or OPENAI_API_KEY).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────

PDF_URL = (
    "https://www.moutaichina.com/mtgf/articleFileDir/"
    "2026-04/17/07cf01cc11a14ea18cfadf9ebe2a4eb3.pdf"
)
COMPANY = "贵州茅台"
TICKER = "600519.SH"
FILING_TYPE = "annual"
PERIOD_END = "2025-12-31"
LANGUAGE = "zh"
DATA_DIR = "data"

# ── Helpers ──────────────────────────────────────────────────────────────


def download_pdf(url: str, dest: Path) -> Path:
    """Download PDF if not already present."""
    if dest.exists():
        print(f"  PDF already exists: {dest}")
        return dest
    print(f"  Downloading {url} ...")
    urllib.request.urlretrieve(url, str(dest))
    print(f"  Saved to {dest} ({dest.stat().st_size / 1024:.0f} KB)")
    return dest


def run_analysis(pdf_path: Path) -> str:
    """Run the jetbot analysis pipeline and return the doc_id."""
    from src.cli import app  # noqa: E402
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(app, [
        "analyze",
        "--pdf", str(pdf_path),
        "--company", COMPANY,
        "--ticker", TICKER,
        "--filing-type", FILING_TYPE,
        "--period-end", PERIOD_END,
        "--language", LANGUAGE,
        "--out", DATA_DIR,
    ])
    if result.exit_code != 0:
        print(f"  Analysis failed:\n{result.output}")
        sys.exit(1)

    # Extract doc_id from output path
    output_line = result.output.strip().split("\n")[-1]
    # "Analysis complete. Report: data/<doc_id>/report/trader_report.md"
    doc_id = output_line.split("/")[-3]
    print(f"  Analysis complete. doc_id: {doc_id}")
    return doc_id


def run_export(doc_id: str, output_path: Path) -> dict:
    """Export financial facts and return the envelope."""
    from src.cli import app  # noqa: E402
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(app, [
        "export-facts", doc_id,
        "--out", DATA_DIR,
        "--output", str(output_path),
    ])
    if result.exit_code != 0:
        print(f"  Export failed:\n{result.output}")
        sys.exit(1)

    with open(output_path, encoding="utf-8") as f:
        envelope = json.load(f)

    print(f"  Exported {len(envelope.get('facts', []))} facts → {output_path}")
    return envelope


def print_facts(envelope: dict) -> None:
    """Pretty-print the core metrics."""
    print(f"\n  {'Metric':<25s} {'Value':>15s}  Label")
    print(f"  {'─' * 25} {'─' * 15}  {'─' * 20}")
    for fact in envelope.get("facts", []):
        print(f"  {fact['metric']:<25s} {fact['value']:>15.6f}  {fact['label']}")


def print_risk_signals(envelope: dict) -> None:
    """Pretty-print risk signals."""
    signals = envelope.get("risk_signals", [])
    if not signals:
        return
    print(f"\n  Risk Signals ({len(signals)}):")
    for sig in signals:
        sev = sig["severity"].upper()
        print(f"  [{sev:6s}] {sig['category']}: {sig['title']}")


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("  贵州茅台 2025 年报 — 跨项目集成端到端案例")
    print("=" * 70)

    # Step 1: Download PDF
    print("\n[Step 1] 下载茅台 2025 年年度报告...")
    examples_dir = Path(__file__).resolve().parent
    pdf_path = examples_dir / "moutai_2025_annual.pdf"
    download_pdf(PDF_URL, pdf_path)

    # Step 2: Run analysis
    print("\n[Step 2] 运行 jetbot 分析管线 (11 nodes)...")
    doc_id = run_analysis(pdf_path)

    # Step 3: Export facts
    print("\n[Step 3] 导出统一格式财务事实 (schema v1.0)...")
    export_path = examples_dir / "moutai_2025_export.json"
    envelope = run_export(doc_id, export_path)
    print_facts(envelope)
    print_risk_signals(envelope)

    # Step 4 (optional): Import into stock
    print("\n[Step 4] 导入 stock 进行基本面过滤...")
    stock_dir = Path(__file__).resolve().parent.parent.parent.parent / "stock"
    if stock_dir.exists():
        # Copy export to stock project
        stock_export_dir = stock_dir / "jetbot_exports"
        stock_export_dir.mkdir(exist_ok=True)
        stock_export_path = stock_export_dir / export_path.name

        with open(stock_export_path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, ensure_ascii=False, indent=2)

        # Run fundamental filter
        try:
            sys.path.insert(0, str(stock_dir))
            from src.data_sources.jetbot_facts import JetbotFactsProvider
            from src.strategies.fundamental_filter import (
                FundamentalFilter,
                FundamentalThresholds,
            )

            provider = JetbotFactsProvider(
                export_dir=str(stock_export_dir),
                min_confidence=0.5,
            )
            filt = FundamentalFilter(provider)
            result = filt.score_symbol(TICKER)
            print(f"  评分结果: {result.summary()}")

            # Also test with relaxed thresholds
            relaxed = FundamentalThresholds(
                revenue_growth_min=-0.05,
                net_profit_growth_min=-0.10,
                gross_margin_min=0.30,
                debt_ratio_max=0.70,
            )
            relaxed_filt = FundamentalFilter(provider, relaxed)
            relaxed_result = relaxed_filt.score_symbol(TICKER)
            print(f"  放宽阈值后: {relaxed_result.summary()}")

            # Build factor DataFrame
            factors = provider.build_fundamental_factors()
            print(f"  因子 DataFrame shape: {factors.shape}")
            print(f"  {factors.to_string()}")

        except ImportError as e:
            print(f"  stock 项目导入失败 (跳过): {e}")
    else:
        print(f"  stock 项目未找到 ({stock_dir})，跳过 Step 4")

    print("\n" + "=" * 70)
    print("  案例运行完成!")
    print(f"  导出文件: {export_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
