# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS builder
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENV=/app/services/user-service/.venv
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app/services/user-service
COPY requirements ./requirements
COPY requirements.txt .
RUN uv venv "${UV_PROJECT_ENV}" && uv pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY run.py .
COPY pyproject.toml ./pyproject.toml
COPY README.md ./README.md

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENV=/app/services/user-service/.venv \
    PATH="/app/services/user-service/.venv/bin:${PATH}" \
    PYTHONPATH="/app/services/user-service"
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app/services/user-service
COPY --from=builder /app/services/user-service/.venv /app/services/user-service/.venv
COPY --from=builder /app/services/user-service/app ./app
COPY --from=builder /app/services/user-service/run.py ./run.py
COPY --from=builder /app/services/user-service/pyproject.toml ./pyproject.toml
COPY --from=builder /app/services/user-service/requirements ./requirements
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app/services/user-service
USER appuser
EXPOSE 5001
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:5001/v1/health || exit 1
ENTRYPOINT ["uv", "run"]
CMD ["python", "run.py"]
