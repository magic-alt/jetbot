# ── Builder stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install -e ".[all]" || \
    pip install --no-cache-dir --prefix=/install -e .

# ── Runtime stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder /app .

# Create non-root user
RUN groupadd -r agent && useradd -r -g agent agent && \
    mkdir -p /app/data && chown -R agent:agent /app

USER agent

EXPOSE 8000
ENV DATA_DIR=/app/data

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
