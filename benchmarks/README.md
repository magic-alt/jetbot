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

Real PDF benchmark manifests should point to local-only files through relative paths such as `raw/company-2025-10k.pdf`. Those raw files are intentionally ignored by git.