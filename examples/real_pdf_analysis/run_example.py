"""Real-PDF example: analyze Apple Inc. FY2024 Q4 Consolidated Financial Statements.

This script downloads a public financial-report PDF from a listed company
(Apple Inc., NASDAQ:AAPL) and runs the full jetbot pipeline against it using
the deterministic mock LLM — no API key required.

Usage:
    python examples/real_pdf_analysis/run_example.py
    python examples/real_pdf_analysis/run_example.py --url <other.pdf>
    python examples/real_pdf_analysis/run_example.py --keep-data

Output is written under `examples/real_pdf_analysis/output/<doc_id>/`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request
from datetime import date
from pathlib import Path

# Default: Apple Inc. (AAPL) Q4 FY2024 Consolidated Financial Statements (small public PDF).
DEFAULT_URL = (
    "https://www.apple.com/newsroom/pdfs/fy2024-q4/"
    "FY24_Q4_Consolidated_Financial_Statements.pdf"
)
DEFAULT_COMPANY = "Apple Inc."
DEFAULT_PERIOD_END = "2024-09-28"
DEFAULT_REPORT_TYPE = "quarterly"
DEFAULT_LANGUAGE = "en"

USER_AGENT = "jetbot-example/0.1 (+https://github.com/magic-alt/jetbot)"

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = EXAMPLE_DIR / "output"


def download_pdf(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"[skip] PDF already present: {dest} ({dest.stat().st_size} bytes)")
        return dest
    print(f"[download] {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    size = dest.stat().st_size
    print(f"[download] OK ({size} bytes)")
    if size < 1024:
        raise RuntimeError(f"Downloaded file is suspiciously small: {size} bytes")
    return dest


def run_pipeline(
    pdf_path: Path,
    out_dir: Path,
    company: str,
    period_end: str,
    report_type: str,
    language: str,
) -> str:
    # Force the mock LLM so the example is fully offline / deterministic.
    os.environ.setdefault("LLM_DEFAULT_MODEL", "mock:mock")

    # Imported lazily so we get a clear error if the project isn't installed.
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
        period_end=date.fromisoformat(period_end),
        report_type=report_type,
        language=language,
    )
    store.save_meta(doc_id, meta)

    state = AgentState(
        doc_meta=meta,
        pdf_path=str(store.doc_dir(doc_id) / "raw.pdf"),
        data_dir=str(out_dir),
    )
    print(f"[run] doc_id={doc_id}")
    build_graph().invoke(state.model_dump())
    return doc_id


def summarize(out_dir: Path, doc_id: str) -> None:
    doc_dir = out_dir / doc_id
    report_md = doc_dir / "report" / "trader_report.md"
    statements = doc_dir / "extracted" / "statements.json"
    signals = doc_dir / "extracted" / "risk_signals.json"

    print("\n===== Outputs =====")
    for p in (statements, signals, report_md):
        marker = "OK " if p.exists() else "-- "
        size = f"{p.stat().st_size} B" if p.exists() else "missing"
        print(f"  {marker}{p.relative_to(EXAMPLE_DIR)}  ({size})")

    if report_md.exists():
        text = report_md.read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:30])
        print("\n===== trader_report.md (first 30 lines) =====")
        print(head)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", default=DEFAULT_URL, help="PDF URL to download")
    p.add_argument("--company", default=DEFAULT_COMPANY)
    p.add_argument("--period-end", default=DEFAULT_PERIOD_END, help="YYYY-MM-DD")
    p.add_argument("--report-type", default=DEFAULT_REPORT_TYPE)
    p.add_argument("--language", default=DEFAULT_LANGUAGE)
    p.add_argument(
        "--keep-data",
        action="store_true",
        help="Do not delete previous example outputs before running.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.keep_data and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    pdf_name = args.url.rsplit("/", 1)[-1] or "report.pdf"
    pdf_path = EXAMPLE_DIR / "fixtures" / pdf_name
    download_pdf(args.url, pdf_path)
    doc_id = run_pipeline(
        pdf_path=pdf_path,
        out_dir=OUTPUT_DIR,
        company=args.company,
        period_end=args.period_end,
        report_type=args.report_type,
        language=args.language,
    )
    summarize(OUTPUT_DIR, doc_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
