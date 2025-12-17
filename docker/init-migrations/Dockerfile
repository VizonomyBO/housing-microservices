FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

COPY packages/shared_data_layer /app/packages/shared_data_layer

RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python -e /app/packages/shared_data_layer

ENV PYTHONPATH=/app/packages \
    PATH="/app/.venv/bin:$PATH" \
    REVISION=head

COPY docker/init-migrations/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
