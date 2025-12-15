# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS builder
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev git curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY packages ./packages
COPY services/ingestion-service ./services/ingestion-service
WORKDIR /app/services/ingestion-service
RUN uv sync --all-extras

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
ENV APP_HOME=/app/services/ingestion-service \
    PATH="/app/services/ingestion-service/.venv/bin:${PATH}" \
    PYTHONPATH="/app/services/ingestion-service/src" \
    UV_PROJECT_ENV="/app/services/ingestion-service/.venv" \
    INGESTION_SERVICE_PORT=8085
RUN useradd --create-home --shell /bin/bash ingestion
WORKDIR ${APP_HOME}
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/services/ingestion-service ${APP_HOME}
RUN chown -R ingestion:ingestion ${APP_HOME} /app/packages
USER ingestion
EXPOSE 8085
ENTRYPOINT ["uv", "run"]
CMD ["uvicorn", "ingestion_service.main:app", "--host", "0.0.0.0", "--port", "8085"]
