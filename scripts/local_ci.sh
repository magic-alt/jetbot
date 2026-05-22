#!/usr/bin/env bash
# Local CI/CD validation script — mirrors .github/workflows/ci.yml
# Run this before committing: ./scripts/local_ci.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v npm >/dev/null 2>&1; then
	echo "ERROR: npm is required to run the full local CI pipeline."
	echo "       Install Node.js 20+ and run 'make web-install' before retrying."
	exit 1
fi

if [ ! -d "web/node_modules" ]; then
	echo "ERROR: web/node_modules is missing."
	echo "       Run 'make web-install' before executing scripts/local_ci.sh."
	exit 1
fi

echo "===== [1/7] Lint (ruff) ====="
python -m ruff check src tests scripts
echo "PASS"

echo ""
echo "===== [2/7] Type check (mypy) ====="
python -m mypy src --ignore-missing-imports
echo "PASS"

echo ""
echo "===== [3/7] Tests (pytest) ====="
python -m pytest -q --timeout=60
echo "PASS"

echo ""
echo "===== [4/7] Eval thresholds ====="
python scripts/eval.py --skip-pytest --thresholds benchmarks/thresholds/golden_minimum.json --output-dir data/eval-local-ci
echo "PASS"

echo ""
echo "===== [5/7] Lint web (eslint) ====="
(cd web && npm run lint)
echo "PASS"

echo ""
echo "===== [6/7] Type-check web (vue-tsc) ====="
(cd web && npm run typecheck)
echo "PASS"

echo ""
echo "===== [7/7] Build web (vite) ====="
(cd web && npm run build)
echo "PASS"

echo ""
echo "===== All local CI checks passed ====="
