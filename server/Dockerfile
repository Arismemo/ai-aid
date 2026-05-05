# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /wheels \
        "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "sse-starlette>=2.1"

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
COPY pyproject.toml ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "sse-starlette>=2.1" \
    && rm -rf /wheels
COPY ai_aid ./ai_aid
COPY migrations ./migrations
COPY migration_runner.py ./
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "ai_aid.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
