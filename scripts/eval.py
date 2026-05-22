"""Evaluation CLI: runs golden cases and reports accuracy metrics."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_OUTPUT_DIR = Path("data") / "eval"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Jetbot financial extraction evaluation.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for eval artifacts.")
    parser.add_argument("--skip-pytest", action="store_true", help="Skip pytest golden gate and only compute metrics.")
    parser.add_argument("--allow-real-llm", action="store_true", help="Do not force the mock LLM provider.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.allow_real_llm:
        _force_mock_llm()

    output_dir = Path(args.output_dir)
    started_at = _utc_now()
    pytest_result = None if args.skip_pytest else _run_pytest_gate()
    case_results = _run_golden_cases(output_dir)
    metrics = _compute_metrics(case_results)
    finished_at = _utc_now()
    report = build_eval_report(
        metrics=metrics,
        case_results=case_results,
        pytest_result=pytest_result,
        started_at=started_at,
        finished_at=finished_at,
    )
    write_eval_report(report, output_dir)
    print(render_markdown_report(report))
    if pytest_result and pytest_result["exit_code"] != 0:
        return int(pytest_result["exit_code"])
    return 0


def build_eval_report(
    *,
    metrics: dict[str, Any],
    case_results: list[dict[str, Any]],
    pytest_result: dict[str, Any] | None,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    status = "passed"
    if pytest_result and pytest_result["exit_code"] != 0:
        status = "failed"
    return {
        "schema_version": 1,
        "suite": "golden",
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "metrics": metrics,
        "cases": [_case_summary(case) for case in case_results],
        "pytest": pytest_result,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# Jetbot Evaluation Report",
        "",
        f"Status: **{report['status']}**",
        f"Suite: `{report['suite']}`",
        f"Cases: {metrics.get('n_cases', 0)}",
        "",
        "## Metrics",
        "",
    ]
    for key, value in metrics.items():
        lines.append(f"- `{key}`: {_format_metric(value)}")
    lines.extend(["", "## Cases", ""])
    for case in report["cases"]:
        lines.append(
            f"- `{case['name']}`: facts={case['fact_count']}, "
            f"statements={','.join(case['statement_types']) or 'none'}, errors={len(case['errors'])}"
        )
    return "\n".join(lines) + "\n"


def write_eval_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "eval_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "eval_report.md").write_text(render_markdown_report(report), encoding="utf-8")


def _case_summary(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": case["name"],
        "statement_types": case["statement_types"],
        "fact_count": case["fact_count"],
        "note_count": len(case.get("notes", [])),
        "risk_signal_count": len(case.get("risk_signals", [])),
        "errors": case["errors"],
    }


def _run_pytest_gate() -> dict[str, Any]:
    import subprocess

    command = [sys.executable, "-m", "pytest", "tests/golden/", "-v", "--tb=short", "-q"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _run_golden_cases(output_dir: Path) -> list[dict[str, Any]]:
    from src.agent.graph import build_graph
    from src.agent.state import AgentState
    from src.finance.facts import facts_from_statements
    from src.schemas.models import DocumentMeta, Page

    graph = build_graph()
    results: list[dict[str, Any]] = []
    for case in _load_golden_cases():
        case_dir = output_dir / "artifacts"
        pages = [Page(page_number=p["page_number"], text=p["text"], images=[]) for p in case["pages"]]
        state = AgentState(
            doc_meta=DocumentMeta(doc_id=f"eval-{case['name']}", filename=f"{case['name']}.pdf"),
            pdf_path=None,
            data_dir=str(case_dir),
            debug={"fake_pages": pages},
        )
        result = AgentState.model_validate(graph.invoke(state.model_dump()))
        facts = result.facts or facts_from_statements(result.doc_meta.doc_id, result.statements)
        expected_facts = _expected_facts(case.get("expected_statements", {}))
        results.append({
            "name": case["name"],
            "statements": result.statements,
            "facts": facts,
            "notes": result.notes,
            "risk_signals": result.risk_signals,
            "expected_totals": case.get("expected_statements", {}),
            "expected_facts": expected_facts,
            "expected_note_types": set(case.get("expected_note_types", [])),
            "expected_signal_categories": set(case.get("expected_signal_categories", [])),
            "statement_types": sorted(result.statements),
            "fact_count": len(facts),
            "errors": result.errors,
        })
    return results


def _compute_metrics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    from src.utils.metrics import compute_golden_metrics

    return compute_golden_metrics(case_results)


def _load_golden_cases() -> list[dict[str, Any]]:
    conftest_path = Path("tests") / "golden" / "conftest.py"
    spec = importlib.util.spec_from_file_location("jetbot_golden_conftest", conftest_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load golden cases from {conftest_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    golden_cases = module.golden_cases

    wrapped = getattr(golden_cases, "__pytest_wrapped__", None)
    if wrapped is not None and getattr(wrapped, "obj", None) is not None:
        return wrapped.obj()
    raw = getattr(golden_cases, "__wrapped__", None)
    if raw is not None:
        return raw()
    return golden_cases()


def _expected_facts(expected_statements: dict[str, dict[str, float]]) -> dict[str, float]:
    expected: dict[str, float] = {}
    for statement_type, totals in expected_statements.items():
        for concept, value in totals.items():
            expected[f"{statement_type}:{concept}"] = value
    return expected


def _force_mock_llm() -> None:
    os.environ["LLM_DEFAULT_MODEL"] = "mock:mock"
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    from src.llm.base import reset_llm_client

    reset_llm_client()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
