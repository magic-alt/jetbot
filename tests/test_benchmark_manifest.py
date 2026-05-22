from __future__ import annotations

import json
from pathlib import Path


def test_benchmark_manifest_schema_and_sample_are_valid_json() -> None:
    schema = json.loads(Path("benchmarks/manifest.schema.json").read_text(encoding="utf-8"))
    sample = json.loads(Path("benchmarks/sample_manifest.json").read_text(encoding="utf-8"))

    assert schema["title"] == "Jetbot Benchmark Manifest"
    assert sample["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert sample["data_policy"]["raw_files_committed"] is False
    assert sample["cases"][0]["expected_facts"][0]["concept"] == "revenue"