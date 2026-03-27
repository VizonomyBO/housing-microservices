FROM python:3.13-slim AS builder
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY services/worldbank-data-service ./services/worldbank-data-service
WORKDIR /app/services/worldbank-data-service
RUN uv sync --all-extras

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
ENV APP_HOME=/app/services/worldbank-data-service \
    PATH="/app/services/worldbank-data-service/.venv/bin:${PATH}" \
    PYTHONPATH="/app/services/worldbank-data-service/src" \
    UV_PROJECT_ENV="/app/services/worldbank-data-service/.venv" \
    WORLDBANK_DATA_SERVICE_PORT=8092
RUN useradd --create-home --shell /bin/bash worldbank
WORKDIR ${APP_HOME}
COPY --from=builder /app/services/worldbank-data-service ${APP_HOME}
RUN chown -R worldbank:worldbank ${APP_HOME}
USER worldbank
EXPOSE 8092
ENTRYPOINT ["uv", "run"]
CMD ["uvicorn", "worldbank_data_service.main:app", "--host", "0.0.0.0", "--port", "8092"]
