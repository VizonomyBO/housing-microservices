# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS builder
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY packages ./packages
COPY services/websocket-service ./services/websocket-service
WORKDIR /app/services/websocket-service
RUN uv sync --all-extras

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
ENV APP_HOME=/app/services/websocket-service \
    PATH="/app/services/websocket-service/.venv/bin:${PATH}" \
    PYTHONPATH="/app/services/websocket-service/src" \
    UV_PROJECT_ENV="/app/services/websocket-service/.venv" \
    WEBSOCKET_SERVICE_PORT=8091
RUN useradd --create-home --shell /bin/bash websocket
WORKDIR ${APP_HOME}
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/services/websocket-service ${APP_HOME}
RUN chown -R websocket:websocket ${APP_HOME} /app/packages
USER websocket
EXPOSE 8091
ENTRYPOINT ["uv", "run"]
CMD ["uvicorn", "websocket_service.main:app", "--host", "0.0.0.0", "--port", "8091"]
