from __future__ import annotations

import json
from pathlib import Path


def test_benchmark_manifest_schema_and_sample_are_valid_json() -> None:
    schema = json.loads(Path("benchmarks/manifest.schema.json").read_text(encoding="utf-8"))
    sample = json.loads(Path("benchmarks/sample_manifest.json").read_text(encoding="utf-8"))

    assert schema["title"] == "Jetbot Benchmark Manifest"
    assert sample["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert sample["data_policy"]["raw_files_committed"] is False
    concepts = {fact["concept"] for fact in sample["cases"][0]["expected_facts"]}
    assert "revenue" in concepts


def test_local_private_manifests_cover_us_filings_and_stress_cases() -> None:
    us_filings = json.loads(Path("benchmarks/local_manifests/us_filings_private_batch.json").read_text(encoding="utf-8"))
    stress = json.loads(Path("benchmarks/local_manifests/stress_private_batch.json").read_text(encoding="utf-8"))

    assert us_filings["benchmark_id"] == "local-private-us-filings-v1"
    assert {case["filing_type"] for case in us_filings["cases"]} == {"10-K", "10-Q"}
    assert all(case["source"]["path"].startswith("../private/us_filings/") for case in us_filings["cases"])

    assert stress["benchmark_id"] == "local-private-stress-v1"
    assert len(stress["cases"]) >= 3
    assert all(case["source"]["path"].startswith("../private/stress/") for case in stress["cases"])


def test_thresholds_include_key_fact_metrics() -> None:
    thresholds = json.loads(Path("benchmarks/thresholds/golden_minimum.json").read_text(encoding="utf-8"))

    assert "fact_accuracy_revenue" in thresholds["min_metrics"]
    assert "fact_accuracy_operating_cash_flow" in thresholds["min_metrics"]