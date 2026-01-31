.PHONY: dev test fmt

dev:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest

fmt:
	python -m ruff format src tests
