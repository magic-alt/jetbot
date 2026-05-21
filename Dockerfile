# ── Builder stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Build-time arg to opt into extra dependency groups, e.g.
#   docker build --build-arg EXTRAS="celery,postgres,s3" -t jetbot .
#   docker build --build-arg EXTRAS="all" -t jetbot .
# Default is base deps only — keeps the image small and the build fast.
ARG EXTRAS=""

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/

RUN if [ -n "$EXTRAS" ]; then \
        pip install --no-cache-dir --prefix=/install -e ".[${EXTRAS}]"; \
    else \
        pip install --no-cache-dir --prefix=/install -e .; \
    fi

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
