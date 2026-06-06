"""Apple FY2024 10-K cross-project integration example.

Downloads the Apple 10-K annual report (FY2024, ending Sep 28 2024),
runs the full jetbot analysis pipeline, exports normalised financial
facts (schema v1.0), and optionally imports into the ``stock`` project
for fundamental filtering.

Usage:
    python examples/apple_10k_analysis/run_example.py
    python examples/apple_10k_analysis/run_example.py --url <other.pdf>
    python examples/apple_10k_analysis/run_example.py --skip-stock
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from datetime import date
from pathlib import Path

# -- Defaults: Apple 10-K FY2024 -----------------------------------------

DEFAULT_URL = (
    "https://www.sec.gov/Archives/edgar/data/320193/"
    "000032019324000123/aapl-20240928.htm"
)
DEFAULT_COMPANY = "Apple Inc."
DEFAULT_TICKER = "AAPL"
DEFAULT_PERIOD_END = "2024-09-28"
DEFAULT_FILING_TYPE = "annual"
DEFAULT_LANGUAGE = "en"

USER_AGENT = "jetbot-example/0.1 (+https://github.com/magic-alt/jetbot)"

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = EXAMPLE_DIR / "output"


# -- PDF download ---------------------------------------------------------


def download_pdf(url: str, dest: Path) -> Path:
    """Download PDF if not already cached."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"[skip] PDF already present: {dest} ({dest.stat().st_size} bytes)")
        return dest
    print(f"[download] {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    size = dest.stat().st_size
    print(f"[download] OK -> {dest} ({size:,} bytes)")
    if size < 1024:
        raise RuntimeError(f"Downloaded file is suspiciously small: {size} bytes")
    return dest


# -- Analysis pipeline ----------------------------------------------------


def run_pipeline(
    pdf_path: Path,
    out_dir: Path,
    company: str,
    ticker: str,
    period_end: str,
    filing_type: str,
    language: str,
) -> str:
    """Run the full jetbot LangGraph pipeline and return doc_id."""
    sys.path.insert(0, str(REPO_ROOT))
    from src.agent.graph import build_graph  # noqa: E402
    from src.agent.state import AgentState  # noqa: E402
    from src.schemas.models import DocumentMeta  # noqa: E402
    from src.storage.local_store import LocalStore  # noqa: E402
    from src.utils.ids import new_doc_id  # noqa: E402

    doc_id = new_doc_id()
    out_dir.mkdir(parents=True, exist_ok=True)
    store = LocalStore(str(out_dir))
    store.save_raw_pdf(doc_id, str(pdf_path))

    meta = DocumentMeta(
        doc_id=doc_id,
        filename=pdf_path.name,
        company=company,
        ticker=ticker,
        period_end=date.fromisoformat(period_end),
        filing_type=filing_type,
        language=language,
    )
    store.save_meta(doc_id, meta)

    state = AgentState(
        doc_meta=meta,
        pdf_path=str(store.doc_dir(doc_id) / "raw.pdf"),
        data_dir=str(out_dir),
    )
    print(f"[analyze] doc_id={doc_id}  company={company}  ticker={ticker}")
    build_graph().invoke(state.model_dump())
    print(f"[analyze] complete -> {out_dir / doc_id / 'report' / 'trader_report.md'}")
    return doc_id


# -- Export ----------------------------------------------------------------


def export_facts(out_dir: Path, doc_id: str, ticker: str) -> dict:
    """Export schema v1.0 financial facts and return the envelope."""
    sys.path.insert(0, str(REPO_ROOT))
    from src.export.builder import build_export  # noqa: E402
    from src.finance.facts import apply_corrections  # noqa: E402
    from src.schemas.models import (  # noqa: E402
        Correction,
        DocumentMeta,
        FinancialFact,
        FinancialStatement,
        RiskSignal,
    )
    from src.storage.local_store import LocalStore  # noqa: E402

    store = LocalStore(str(out_dir))

    meta = DocumentMeta.model_validate(store.load_meta(doc_id))
    stmts_raw = store.load_json(doc_id, "extracted/statements.json") or {}
    statements = {key: FinancialStatement.model_validate(val) for key, val in stmts_raw.items()}

    facts_raw = store.load_json(doc_id, "extracted/facts.json") or []
    facts = [FinancialFact.model_validate(f) for f in facts_raw]

    corrections_raw = store.load_json(doc_id, "extracted/corrections.json") or []
    corrections = [Correction.model_validate(c) for c in corrections_raw]
    if corrections:
        facts = apply_corrections(facts, corrections)

    signals_raw = store.load_json(doc_id, "extracted/risk_signals.json") or []
    risk_signals = [RiskSignal.model_validate(s) for s in signals_raw]

    envelope = build_export(
        meta=meta,
        statements=statements,
        facts=facts,
        risk_signals=risk_signals,
        corrections_applied=bool(corrections),
    )

    export_path = out_dir / doc_id / "exported_facts.json"
    export_path.write_text(
        json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    data = envelope.model_dump(mode="json")
    n_facts = len(data.get("facts", []))
    n_signals = len(data.get("risk_signals", []))
    print(f"[export] {n_facts} facts, {n_signals} risk signals -> {export_path}")
    return data


def print_core_metrics(envelope: dict) -> None:
    """Pretty-print the 5 core metrics."""
    facts = envelope.get("facts", [])
    if not facts:
        print("[export] No core metrics computed.")
        return
    print(f"\n  {'Metric':<25s} {'Value':>18s}  Label")
    print(f"  {'─' * 25} {'─' * 18}  {'─' * 15}")
    for f in facts:
        v = f["value"]
        formatted = f"{v:.4f}" if abs(v) < 10 else f"{v:,.2f}"
        print(f"  {f['metric']:<25s} {formatted:>18s}  {f['label']}")


def print_risk_signals(envelope: dict) -> None:
    """Pretty-print risk signals."""
    signals = envelope.get("risk_signals", [])
    if not signals:
        return
    print(f"\n  Risk Signals ({len(signals)}):")
    for sig in signals:
        sev = sig["severity"].upper()
        print(f"  [{sev:6s}] {sig['category']}: {sig['title']}")


# -- Cross-project: stock integration ------------------------------------


def try_stock_integration(envelope: dict, ticker: str) -> None:
    """If the stock project is a sibling, run FundamentalFilter demo."""
    stock_dir = REPO_ROOT.parent / "stock"
    if not stock_dir.exists():
        print("\n[stock] stock project not found (expected sibling of jetbot), skipping")
        return

    stock_export_dir = stock_dir / "jetbot_exports"
    stock_export_dir.mkdir(exist_ok=True)
    export_dest = stock_export_dir / "apple_fy2024_export.json"
    with open(export_dest, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)
    print(f"\n[stock] Export copied to {export_dest}")

    try:
        sys.path.insert(0, str(stock_dir))
        from src.data_sources.jetbot_facts import JetbotFactsProvider  # noqa: E402
        from src.strategies.fundamental_filter import (  # noqa: E402
            FundamentalFilter,
            FundamentalThresholds,
        )

        provider = JetbotFactsProvider(export_dir=str(stock_export_dir), min_confidence=0.5)
        envelopes = provider.load()
        print(f"[stock] Loaded {len(envelopes)} export envelope(s)")

        # Default thresholds
        filt = FundamentalFilter(provider)
        result = filt.score_symbol(ticker)
        print(f"[stock] Default thresholds: {result.summary()}")

        # Relaxed thresholds (allow one-time tax charge impact)
        relaxed = FundamentalThresholds(
            revenue_growth_min=0.0,
            net_profit_growth_min=-0.10,
            gross_margin_min=0.30,
            debt_ratio_max=0.85,
        )
        relaxed_filt = FundamentalFilter(provider, relaxed)
        relaxed_result = relaxed_filt.score_symbol(ticker)
        print(f"[stock] Relaxed thresholds: {relaxed_result.summary()}")

        # Factor DataFrame
        factors = provider.build_fundamental_factors()
        print(f"[stock] Factor DataFrame shape: {factors.shape}")
        print(f"  {factors.to_string()}")

    except ImportError as exc:
        print(f"[stock] Import failed (skipped): {exc}")


# -- Summarize ------------------------------------------------------------


def summarize(out_dir: Path, doc_id: str) -> None:
    """Print output file summary."""
    doc_dir = out_dir / doc_id
    report_md = doc_dir / "report" / "trader_report.md"
    statements = doc_dir / "extracted" / "statements.json"
    signals = doc_dir / "extracted" / "risk_signals.json"
    export_json = doc_dir / "exported_facts.json"

    print("\n===== Output Files =====")
    for p in (statements, signals, export_json, report_md):
        marker = "OK " if p.exists() else "-- "
        size = f"{p.stat().st_size:,} B" if p.exists() else "missing"
        print(f"  {marker}{p.relative_to(EXAMPLE_DIR)}  ({size})")

    if report_md.exists():
        text = report_md.read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:30])
        print("\n===== trader_report.md (first 30 lines) =====")
        print(head)


# -- CLI ------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", default=DEFAULT_URL, help="PDF URL to download")
    p.add_argument("--company", default=DEFAULT_COMPANY)
    p.add_argument("--ticker", default=DEFAULT_TICKER)
    p.add_argument("--period-end", default=DEFAULT_PERIOD_END, help="YYYY-MM-DD")
    p.add_argument("--filing-type", default=DEFAULT_FILING_TYPE)
    p.add_argument("--language", default=DEFAULT_LANGUAGE)
    p.add_argument(
        "--keep-data",
        action="store_true",
        help="Do not delete previous example outputs before running.",
    )
    p.add_argument(
        "--skip-stock",
        action="store_true",
        help="Skip the cross-project stock integration step.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.keep_data and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    print("=" * 70)
    print("  Apple FY2024 10-K -- jetbot -> stock cross-project integration")
    print("=" * 70)

    # Step 1: Download PDF
    print("\n[Step 1] Downloading 10-K PDF...")
    pdf_name = args.url.rsplit("/", 1)[-1] or "report.pdf"
    pdf_path = EXAMPLE_DIR / "fixtures" / pdf_name
    download_pdf(args.url, pdf_path)

    # Step 2: Run analysis pipeline
    print("\n[Step 2] Running jetbot analysis pipeline...")
    doc_id = run_pipeline(
        pdf_path=pdf_path,
        out_dir=OUTPUT_DIR,
        company=args.company,
        ticker=args.ticker,
        period_end=args.period_end,
        filing_type=args.filing_type,
        language=args.language,
    )

    # Step 3: Export facts
    print("\n[Step 3] Exporting financial facts (schema v1.0)...")
    envelope = export_facts(OUTPUT_DIR, doc_id, args.ticker)
    print_core_metrics(envelope)
    print_risk_signals(envelope)

    # Step 4: Summarize outputs
    print("\n[Step 4] Output summary...")
    summarize(OUTPUT_DIR, doc_id)

    # Step 5: Cross-project stock integration
    if not args.skip_stock:
        print("\n[Step 5] Cross-project: stock fundamental filter...")
        try_stock_integration(envelope, args.ticker)

    print("\n" + "=" * 70)
    print("  Example complete!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
