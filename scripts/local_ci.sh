#!/usr/bin/env bash
# Local CI/CD validation script — mirrors .github/workflows/ci.yml
# Run this before committing: ./scripts/local_ci.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "===== [1/3] Lint (ruff) ====="
python -m ruff check src tests
echo "PASS"

echo ""
echo "===== [2/3] Type check (mypy) ====="
python -m mypy src --ignore-missing-imports
echo "PASS"

echo ""
echo "===== [3/3] Tests (pytest) ====="
python -m pytest -q --timeout=60
echo "PASS"

echo ""
echo "===== All local CI checks passed ====="
