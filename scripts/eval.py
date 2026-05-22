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
KEY_FACTS: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue",),
    "gross_profit": ("gross_profit",),
    "operating_income": ("operating_income",),
    "net_income": ("net_income",),
    "total_assets": ("total_assets",),
    "total_liabilities": ("total_liabilities",),
    "total_equity": ("total_equity",),
    "operating_cash_flow": ("operating_cash_flow", "operating_cf"),
    "capex": ("capex",),
    "cash_and_equivalents": ("cash_and_equivalents",),
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Jetbot financial extraction evaluation.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for eval artifacts.")
    parser.add_argument(
        "--benchmark-manifest",
        help="Optional benchmark manifest JSON. When set, run that local benchmark dataset instead of the built-in golden cases.",
    )
    parser.add_argument("--thresholds", help="Optional JSON file with min_metrics/max_metrics quality gates.")
    parser.add_argument("--skip-pytest", action="store_true", help="Skip pytest golden gate and only compute metrics.")
    parser.add_argument("--allow-real-llm", action="store_true", help="Do not force the mock LLM provider.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.allow_real_llm:
        _force_mock_llm()

    output_dir = Path(args.output_dir)
    started_at = _utc_now()
    benchmark_manifest = load_benchmark_manifest(args.benchmark_manifest)
    pytest_result = None if args.skip_pytest or benchmark_manifest else _run_pytest_gate()
    if benchmark_manifest:
        case_results = _run_benchmark_manifest(benchmark_manifest, Path(args.benchmark_manifest), output_dir)
        suite = benchmark_manifest["benchmark_id"]
        dataset = {
            "benchmark_id": benchmark_manifest["benchmark_id"],
            "name": benchmark_manifest.get("name"),
            "manifest_path": str(Path(args.benchmark_manifest)),
            "data_policy": benchmark_manifest.get("data_policy"),
        }
    else:
        case_results = _run_golden_cases(output_dir)
        suite = "golden"
        dataset = None
    metrics = _compute_metrics(case_results)
    threshold_results = evaluate_thresholds(metrics, load_thresholds(args.thresholds) if args.thresholds else None)
    finished_at = _utc_now()
    report = build_eval_report(
        suite=suite,
        metrics=metrics,
        case_results=case_results,
        pytest_result=pytest_result,
        threshold_results=threshold_results,
        started_at=started_at,
        finished_at=finished_at,
        dataset=dataset,
    )
    write_eval_report(report, output_dir)
    print(render_markdown_report(report))
    if pytest_result and pytest_result["exit_code"] != 0:
        return int(pytest_result["exit_code"])
    if threshold_results["status"] == "failed":
        return 2
    return 0


def build_eval_report(
    *,
    suite: str = "golden",
    metrics: dict[str, Any],
    case_results: list[dict[str, Any]],
    pytest_result: dict[str, Any] | None,
    threshold_results: dict[str, Any] | None = None,
    started_at: str,
    finished_at: str,
    dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = "passed"
    if pytest_result and pytest_result["exit_code"] != 0:
        status = "failed"
    threshold_results = threshold_results or {"status": "skipped", "checks": []}
    if threshold_results["status"] == "failed":
        status = "failed"
    return {
        "schema_version": 1,
        "suite": suite,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "metrics": metrics,
        "cases": [_case_summary(case) for case in case_results],
        "dataset": dataset,
        "thresholds": threshold_results,
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
    dataset = report.get("dataset")
    if dataset:
        lines.extend([
            "## Dataset",
            "",
            f"Benchmark: `{dataset['benchmark_id']}`",
            f"Manifest: `{dataset['manifest_path']}`",
            "",
        ])
    for key, value in metrics.items():
        lines.append(f"- `{key}`: {_format_metric(value)}")
    thresholds = report.get("thresholds", {"status": "skipped", "checks": []})
    lines.extend(["", "## Thresholds", "", f"Status: **{thresholds['status']}**"])
    for check in thresholds.get("checks", []):
        comparator = ">=" if check["kind"] == "min" else "<="
        lines.append(
            f"- `{check['metric']}`: {_format_metric(check.get('actual'))} "
            f"{comparator} {_format_metric(check['threshold'])} -> {check['status']}"
        )
    lines.extend(["", "## Cases", ""])
    for case in report["cases"]:
        case_metrics = case.get("metrics", {})
        lines.append(
            f"- `{case['name']}` ({case['source_type']}): facts={case['fact_count']}, "
            f"statements={','.join(case['statement_types']) or 'none'}, errors={len(case['errors'])}, "
            f"fact_accuracy={_format_metric(case_metrics.get('fact_value_accuracy'))}, "
            f"source_refs={_format_metric(case_metrics.get('fact_source_ref_completeness'))}, "
            f"note_recall={_format_metric(case_metrics.get('note_type_recall'))}, "
            f"signal_recall={_format_metric(case_metrics.get('signal_category_recall'))}"
        )
    return "\n".join(lines) + "\n"


def write_eval_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "eval_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "eval_report.md").write_text(render_markdown_report(report), encoding="utf-8")


def load_thresholds(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_benchmark_manifest(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None

    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError(f"Unsupported benchmark manifest schema_version: {manifest.get('schema_version')}")
    if not manifest.get("benchmark_id"):
        raise ValueError("Benchmark manifest requires a non-empty benchmark_id")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark manifest requires at least one case")
    return manifest


def evaluate_thresholds(metrics: dict[str, Any], thresholds: dict[str, Any] | None) -> dict[str, Any]:
    if not thresholds:
        return {"status": "skipped", "checks": []}

    checks: list[dict[str, Any]] = []
    failed = False
    for metric, threshold in thresholds.get("min_metrics", {}).items():
        actual = metrics.get(metric)
        passed = _is_number(actual) and float(actual) >= float(threshold)
        failed = failed or not passed
        checks.append(_threshold_check("min", metric, actual, threshold, passed))
    for metric, threshold in thresholds.get("max_metrics", {}).items():
        actual = metrics.get(metric)
        passed = _is_number(actual) and float(actual) <= float(threshold)
        failed = failed or not passed
        checks.append(_threshold_check("max", metric, actual, threshold, passed))
    return {"status": "failed" if failed else "passed", "checks": checks}


def _threshold_check(kind: str, metric: str, actual: Any, threshold: Any, passed: bool) -> dict[str, Any]:
    return {
        "kind": kind,
        "metric": metric,
        "actual": actual,
        "threshold": threshold,
        "status": "passed" if passed else "failed",
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _case_summary(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": case["name"],
        "source_type": case.get("source_type", "synthetic"),
        "source_path": case.get("source_path"),
        "statement_types": case["statement_types"],
        "fact_count": case["fact_count"],
        "expected_fact_count": len(case.get("expected_facts", {})),
        "note_count": len(case.get("notes", [])),
        "risk_signal_count": len(case.get("risk_signals", [])),
        "metrics": _case_metrics(case),
        "errors": case["errors"],
    }


def _case_metrics(case: dict[str, Any]) -> dict[str, Any]:
    from src.utils.metrics import (
        balance_equation_pass_rate,
        fact_source_ref_completeness,
        fact_value_accuracy,
        note_type_recall,
        signal_category_recall,
        source_ref_completeness,
        statement_accuracy,
    )

    statements = case.get("statements", {})
    expected_totals = case.get("expected_totals", {})
    statement_metrics: dict[str, float] = {}
    for statement_type, totals in expected_totals.items():
        if statement_type in statements and totals:
            statement_metrics[statement_type] = statement_accuracy(statements[statement_type], totals)["accuracy"]

    actual_categories = {signal.category for signal in case.get("risk_signals", [])}
    actual_note_types = {note.note_type for note in case.get("notes", [])}
    expected_facts = case.get("expected_facts", {})
    facts = case.get("facts", [])
    return {
        "statement_accuracy_by_type": statement_metrics,
        "balance_equation_pass": balance_equation_pass_rate([statements]) if statements else None,
        "source_ref_completeness": source_ref_completeness(case.get("notes", []), case.get("risk_signals", [])),
        "fact_value_accuracy": fact_value_accuracy(facts, expected_facts)["accuracy"] if expected_facts else None,
        "fact_source_ref_completeness": fact_source_ref_completeness(facts),
        "signal_category_recall": signal_category_recall(actual_categories, case.get("expected_signal_categories", set())),
        "note_type_recall": note_type_recall(actual_note_types, case.get("expected_note_types", set())),
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

    graph = build_graph()
    results: list[dict[str, Any]] = []
    for case in _load_golden_cases():
        results.append(
            _run_case(
                graph,
                {
                    "name": case["name"],
                    "doc_id": f"eval-{case['name']}",
                    "filename": f"{case['name']}.pdf",
                    "pages": case["pages"],
                    "source_type": "synthetic",
                    "source_path": None,
                    "expected_totals": case.get("expected_statements", {}),
                    "expected_facts": _golden_expected_facts(case),
                    "expected_note_types": set(case.get("expected_note_types", [])),
                    "expected_signal_categories": set(case.get("expected_signal_categories", [])),
                },
                output_dir,
            )
        )
    return results


def _run_benchmark_manifest(
    manifest: dict[str, Any],
    manifest_path: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    from src.agent.graph import build_graph

    graph = build_graph()
    manifest_dir = manifest_path.parent
    results: list[dict[str, Any]] = []
    for case in manifest.get("cases", []):
        results.append(_run_case(graph, _manifest_case_spec(case, manifest_dir), output_dir))
    return results


def _run_case(graph: Any, case: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    from src.agent.state import AgentState
    from src.finance.facts import facts_from_statements

    state = _build_case_state(case, output_dir / "artifacts" / case["name"])
    result = AgentState.model_validate(graph.invoke(state.model_dump()))
    facts = result.facts or facts_from_statements(result.doc_meta.doc_id, result.statements)
    return {
        "name": case["name"],
        "source_type": case.get("source_type", "synthetic"),
        "source_path": case.get("source_path"),
        "statements": result.statements,
        "facts": facts,
        "notes": result.notes,
        "risk_signals": result.risk_signals,
        "expected_totals": case.get("expected_totals", {}),
        "expected_facts": case.get("expected_facts", {}),
        "expected_note_types": case.get("expected_note_types", set()),
        "expected_signal_categories": case.get("expected_signal_categories", set()),
        "statement_types": sorted(result.statements),
        "fact_count": len(facts),
        "errors": result.errors,
    }


def _build_case_state(case: dict[str, Any], case_dir: Path):
    from src.agent.state import AgentState
    from src.schemas.models import DocumentMeta, Page

    pages = case.get("pages")
    if pages is not None:
        fake_pages = [Page(page_number=page["page_number"], text=page["text"], images=[]) for page in pages]
        return AgentState(
            doc_meta=DocumentMeta(doc_id=case["doc_id"], filename=case["filename"]),
            pdf_path=None,
            data_dir=str(case_dir),
            debug={"fake_pages": fake_pages},
        )

    return AgentState(
        doc_meta=DocumentMeta(doc_id=case["doc_id"], filename=case["filename"]),
        pdf_path=case.get("pdf_path"),
        data_dir=str(case_dir),
    )


def _manifest_case_spec(case: dict[str, Any], manifest_dir: Path) -> dict[str, Any]:
    source = case["source"]
    source_type = source["type"]
    source_path = _resolve_source_path(source["path"], manifest_dir)
    expected_fact_entries = case.get("expected_facts", [])
    pages = _load_synthetic_pages(source_path) if source_type == "synthetic" else None
    pdf_path = str(source_path) if source_type == "pdf" else None
    if source_type not in {"synthetic", "pdf"}:
        raise ValueError(
            f"Unsupported benchmark source type '{source_type}'. The current eval runner supports synthetic fixtures and local PDFs."
        )

    return {
        "name": case["case_id"],
        "doc_id": f"eval-{case['case_id']}",
        "filename": source_path.name,
        "pages": pages,
        "pdf_path": pdf_path,
        "source_type": source_type,
        "source_path": str(source_path),
        "expected_totals": _expected_totals_from_fact_entries(expected_fact_entries),
        "expected_facts": _expected_facts_from_manifest(expected_fact_entries),
        "expected_note_types": set(case.get("expected_notes", [])),
        "expected_signal_categories": set(case.get("expected_risk_categories", [])),
    }


def _resolve_source_path(raw_path: str, manifest_dir: Path) -> Path:
    source_path = Path(raw_path)
    if not source_path.is_absolute():
        source_path = manifest_dir / source_path
    if not source_path.exists():
        raise FileNotFoundError(f"Benchmark source file not found: {source_path}")
    return source_path


def _load_synthetic_pages(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pages = payload.get("pages") if isinstance(payload, dict) else payload
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"Synthetic benchmark fixture must contain a non-empty pages list: {path}")
    return pages


def _expected_facts_from_manifest(expected_facts: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for fact in expected_facts:
        if "value" not in fact:
            continue
        values[f"{fact['statement_type']}:{fact['concept']}"] = float(fact["value"])
    return values


def _expected_totals_from_fact_entries(expected_facts: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for fact in expected_facts:
        statement_type = fact.get("statement_type")
        concept = fact.get("concept")
        value = fact.get("value")
        if statement_type not in {"income", "balance", "cashflow"} or concept is None or value is None:
            continue
        totals.setdefault(statement_type, {})[concept] = float(value)
    return totals


def _compute_metrics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    from src.utils.metrics import compute_golden_metrics

    metrics = compute_golden_metrics(case_results)
    metrics.update(_critical_fact_metrics(case_results))
    return metrics


def _critical_fact_metrics(case_results: list[dict[str, Any]]) -> dict[str, float]:
    from src.utils.metrics import fact_value_accuracy

    counts = {metric_name: {"matched": 0, "expected": 0} for metric_name in KEY_FACTS}
    for case in case_results:
        expected_facts = case.get("expected_facts", {})
        for key, expected_value in expected_facts.items():
            concept = key.split(":", 1)[-1]
            metric_name = _key_fact_metric_name(concept)
            if metric_name is None:
                continue
            counts[metric_name]["expected"] += 1
            result = fact_value_accuracy(case.get("facts", []), {key: expected_value})
            if result["accuracy"] == 1.0:
                counts[metric_name]["matched"] += 1

    metrics: dict[str, float] = {}
    for concept, summary in counts.items():
        if summary["expected"]:
            metrics[f"fact_accuracy_{concept}"] = summary["matched"] / summary["expected"]
    return metrics


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


def _golden_expected_facts(case: dict[str, Any]) -> dict[str, float]:
    expected = _expected_facts(case.get("expected_statements", {}))
    extra = case.get("expected_facts", {})
    if isinstance(extra, dict):
        expected.update({str(key): float(value) for key, value in extra.items()})
    elif isinstance(extra, list):
        expected.update(_expected_facts_from_manifest(extra))
    return expected


def _key_fact_metric_name(concept: str) -> str | None:
    for metric_name, aliases in KEY_FACTS.items():
        if concept in aliases:
            return metric_name
    return None


def _force_mock_llm() -> None:
    os.environ["LLM_DEFAULT_MODEL"] = "mock:mock"
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    from src.llm.base import reset_llm_client

    reset_llm_client()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_metric(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
