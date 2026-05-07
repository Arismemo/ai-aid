FROM python:3.12-slim AS builder
WORKDIR /build
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=180
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /wheels \
        "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "sse-starlette>=2.1" \
        "python-multipart>=0.0.9"

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY pyproject.toml ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "sse-starlette>=2.1" \
    "python-multipart>=0.0.9" \
    && rm -rf /wheels
COPY ai_aid ./ai_aid
COPY migrations ./migrations
COPY migration_runner.py ./
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)" || exit 1
CMD ["uvicorn", "ai_aid.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
