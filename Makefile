.PHONY: dev test fmt lint typecheck worker

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
