from __future__ import annotations

import json
from pathlib import Path

import scripts.eval as eval_script
from scripts.eval import build_eval_report, evaluate_thresholds, render_markdown_report, write_eval_report


def test_eval_report_writer_creates_json_and_markdown(tmp_path: Path) -> None:
    report = build_eval_report(
        metrics={"n_cases": 1, "avg_fact_value_accuracy": 1.0},
        case_results=[{"name": "case-a", "fact_count": 2, "statement_types": ["income"], "errors": []}],
        pytest_result={"exit_code": 0, "command": ["pytest"], "stdout": "", "stderr": ""},
        threshold_results={"status": "passed", "checks": []},
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
    )

    write_eval_report(report, tmp_path)

    assert (tmp_path / "eval_report.json").exists()
    assert (tmp_path / "eval_report.md").exists()
    assert "avg_fact_value_accuracy" in render_markdown_report(report)


def test_eval_report_marks_pytest_failure() -> None:
    report = build_eval_report(
        metrics={"n_cases": 0},
        case_results=[],
        pytest_result={"exit_code": 1, "command": ["pytest"], "stdout": "", "stderr": "failed"},
        threshold_results={"status": "skipped", "checks": []},
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
    )

    assert report["status"] == "failed"


def test_thresholds_pass_when_metrics_meet_minimums() -> None:
    result = evaluate_thresholds(
        {"avg_fact_value_accuracy": 0.9, "n_cases": 5},
        {"min_metrics": {"avg_fact_value_accuracy": 0.8, "n_cases": 5}},
    )

    assert result["status"] == "passed"
    assert all(check["status"] == "passed" for check in result["checks"])


def test_thresholds_fail_when_metric_is_below_minimum() -> None:
    result = evaluate_thresholds(
        {"avg_fact_value_accuracy": 0.7},
        {"min_metrics": {"avg_fact_value_accuracy": 0.8}},
    )

    assert result["status"] == "failed"
    assert result["checks"][0] == {
        "kind": "min",
        "metric": "avg_fact_value_accuracy",
        "actual": 0.7,
        "threshold": 0.8,
        "status": "failed",
    }


def test_eval_report_marks_threshold_failure() -> None:
    report = build_eval_report(
        metrics={"avg_fact_value_accuracy": 0.7},
        case_results=[],
        pytest_result={"exit_code": 0, "command": ["pytest"], "stdout": "", "stderr": ""},
        threshold_results={"status": "failed", "checks": []},
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
    )

    assert report["status"] == "failed"


def test_main_returns_nonzero_when_thresholds_fail(tmp_path: Path, monkeypatch) -> None:
    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(json.dumps({"min_metrics": {"avg_fact_value_accuracy": 0.9}}), encoding="utf-8")

    monkeypatch.setattr(eval_script, "_force_mock_llm", lambda: None)
    monkeypatch.setattr(eval_script, "_run_golden_cases", lambda output_dir: [])
    monkeypatch.setattr(eval_script, "_compute_metrics", lambda case_results: {"avg_fact_value_accuracy": 0.5})

    exit_code = eval_script.main([
        "--skip-pytest",
        "--thresholds",
        str(thresholds),
        "--output-dir",
        str(tmp_path / "out"),
    ])

    assert exit_code == 2
    report = json.loads((tmp_path / "out" / "eval_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["thresholds"]["checks"][0]["status"] == "failed"


def test_main_runs_sample_benchmark_manifest_and_writes_document_metrics(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    exit_code = eval_script.main([
        "--benchmark-manifest",
        "benchmarks/sample_manifest.json",
        "--skip-pytest",
        "--output-dir",
        str(output_dir),
    ])

    assert exit_code == 0
    report = json.loads((output_dir / "eval_report.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "eval_report.md").read_text(encoding="utf-8")

    assert report["suite"] == "synthetic-smoke-v1"
    assert report["dataset"]["benchmark_id"] == "synthetic-smoke-v1"
    assert report["cases"][0]["metrics"]["fact_value_accuracy"] is not None
    assert "fact_accuracy_revenue" in report["metrics"]
    assert "## Dataset" in markdown
    assert "synthetic-income-001" in markdown


def test_manifest_case_spec_supports_local_pdf_sources(tmp_path: Path) -> None:
    pdf_path = tmp_path / "local-report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%synthetic\n")

    case = eval_script._manifest_case_spec(
        {
            "case_id": "local-pdf-001",
            "source": {"type": "pdf", "path": pdf_path.name},
            "expected_facts": [
                {"statement_type": "balance", "concept": "total_assets", "value": 10.0},
            ],
        },
        tmp_path,
    )

    assert case["pdf_path"] == str(pdf_path)
    assert case["pages"] is None
    assert case["expected_totals"]["balance"]["total_assets"] == 10.0


def test_critical_fact_metrics_alias_operating_cash_flow() -> None:
    result = eval_script._critical_fact_metrics([
        {
            "facts": [
                type("Fact", (), {"concept": "operating_cf", "statement_type": "cashflow", "value": 42.0})(),
            ],
            "expected_facts": {"cashflow:operating_cash_flow": 42.0},
        }
    ])

    assert result["fact_accuracy_operating_cash_flow"] == 1.0