# Benchmark Manifests

This directory stores committed benchmark metadata for Jetbot evaluation. It is for manifests, schemas, anonymized labels, synthetic fixtures, and quality threshold configs only.

Do commit:

- `manifest.schema.json`
- anonymized benchmark manifests
- synthetic fixture metadata
- expected facts, expected evidence pointers, expected note/risk labels
- threshold configs under `thresholds/`

Do not commit:

- raw third-party or proprietary PDFs
- private customer reports
- non-anonymized analyst labels
- generated eval outputs
- files under `benchmarks/raw/` or `benchmarks/private/`

Run the current golden evaluation gate with:

```bash
python scripts/eval.py --thresholds benchmarks/thresholds/golden_minimum.json
```

Run the sample local benchmark manifest with:

```bash
python scripts/eval.py --benchmark-manifest benchmarks/sample_manifest.json --skip-pytest --output-dir data/eval-dev
```

Run the first local private filing batches after placing raw PDFs under ignored paths:

```bash
python scripts/eval.py --benchmark-manifest benchmarks/local_manifests/us_filings_private_batch.json --skip-pytest --output-dir data/eval-us-private
python scripts/eval.py --benchmark-manifest benchmarks/local_manifests/stress_private_batch.json --skip-pytest --output-dir data/eval-stress-private
```

Real PDF benchmark manifests should point to local-only files through relative paths such as `raw/company-2025-10k.pdf`. Those raw files are intentionally ignored by git.
The current eval runner supports committed `synthetic` fixtures and local `pdf` sources from a manifest.
The committed manifests under `benchmarks/local_manifests/` are safe to commit because they only store anonymized metadata and expected facts; the raw PDFs still live under ignored paths such as `benchmarks/private/us_filings/` and `benchmarks/private/stress/`.
