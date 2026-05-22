from __future__ import annotations

from pathlib import Path

from scripts.eval import build_eval_report, render_markdown_report, write_eval_report


def test_eval_report_writer_creates_json_and_markdown(tmp_path: Path) -> None:
    report = build_eval_report(
        metrics={"n_cases": 1, "avg_fact_value_accuracy": 1.0},
        case_results=[{"name": "case-a", "fact_count": 2, "statement_types": ["income"], "errors": []}],
        pytest_result={"exit_code": 0, "command": ["pytest"], "stdout": "", "stderr": ""},
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
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
    )

    assert report["status"] == "failed"