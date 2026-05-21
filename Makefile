.PHONY: dev test fmt lint typecheck worker eval docker-build docker-up docker-down web-install web-dev web-build web-lint

# === Development ===
dev:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest

fmt:
	python -m ruff format src tests

lint:
	python -m ruff check src tests

typecheck:
	python -m mypy src --ignore-missing-imports

# === Task Queue (Phase 4) ===
worker:
	celery -A src.tasks worker --loglevel=info --concurrency=2

# === Evaluation (Phase 6) ===
eval:
	python -m pytest tests/golden/ -v --tb=short

# === Docker (Phase 7) ===
docker-build:
	docker build -t jetbot:latest .

docker-up:
	docker compose up -d --build
	python scripts/open_ui_after_docker.py

docker-down:
	docker compose down

# === Web UI (Vue 3 + Vite) ===
web-install:
	cd web && npm ci

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm ci && npm run build

web-lint:
	cd web && npm run lint && npm run typecheck
