# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS builder
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENV=/app/services/auth-service/.venv
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app/services/auth-service
COPY requirements ./requirements
RUN uv venv "${UV_PROJECT_ENV}" && uv pip install --no-cache-dir -r requirements/base.txt
COPY app ./app
COPY run.py .
COPY pyproject.toml ./pyproject.toml
COPY pytest.ini ./pytest.ini
COPY tests ./tests

FROM builder AS test
RUN uv pip install --no-cache-dir -r requirements/dev.txt && \
    uv pip install --no-cache-dir -r requirements/test.txt
WORKDIR /app/services/auth-service
CMD ["uv", "run", "pytest", "tests", "-v"]

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENV=/app/services/auth-service/.venv \
    PATH="/app/services/auth-service/.venv/bin:${PATH}" \
    PYTHONPATH="/app/services/auth-service"
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app/services/auth-service
COPY --from=builder /app/services/auth-service/.venv /app/services/auth-service/.venv
COPY --from=builder /app/services/auth-service/app ./app
COPY --from=builder /app/services/auth-service/run.py ./run.py
COPY --from=builder /app/services/auth-service/pyproject.toml ./pyproject.toml
COPY --from=builder /app/services/auth-service/requirements ./requirements
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app/services/auth-service
USER appuser
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1
ENTRYPOINT ["uv", "run"]
CMD ["python", "run.py"]
