"""Application factory for the Agent API FastAPI service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from shared_data_layer.db.session import DatabaseSessionManager

from agent_api.http.errors import GatewayError, error_payload
from agent_api.http.routes.chat import router as chat_router
from agent_api.http.routes.metrics import router as metrics_router
from agent_api.settings import Settings, load_settings
from cache import InMemoryValkeyClient, ValkeyAsyncClient
from telemetry import CacheObservability, get_metrics_registry

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        registry = get_metrics_registry()
        app.state.metrics_registry = registry
        app.state.cache_observability = CacheObservability(
            metrics=registry, namespace=settings.metrics_namespace
        )
        app.state.settings = settings

        app.state.valkey_client = await _initialize_cache_client(
            settings=settings,
            observability=app.state.cache_observability,
        )

        db_initialized = False
        if settings.database_url:
            DatabaseSessionManager.init(settings.database_url)
            db_initialized = True
        else:  # pragma: no cover - configuration edge case
            logger.warning("DATABASE_URL not configured; telemetry DB writes are disabled")
        app.state.db_initialized = db_initialized

        try:
            yield
        finally:
            if db_initialized:
                await DatabaseSessionManager.dispose()
            cache_client = getattr(app.state, "valkey_client", None)
            if isinstance(cache_client, ValkeyAsyncClient):
                await cache_client.close()

    app = FastAPI(
        title="Agent API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def inject_request_id(request: Request, call_next):
        request_id = request.headers.get("Viz-Request-Id") or f"viz-{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["Viz-Request-Id"] = request_id
        return response

    app.include_router(chat_router)
    app.include_router(metrics_router)

    @app.exception_handler(GatewayError)
    async def handle_gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=exc.code,
                message=exc.message,
                request_id=getattr(request.state, "request_id", None),
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="VALIDATION_ERROR",
                message="Request payload failed validation",
                request_id=getattr(request.state, "request_id", None),
                details={"errors": exc.errors()},
            ),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        code = "INTERNAL_ERROR" if exc.status_code >= 500 else "BAD_REQUEST"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=code,
                message=exc.detail or "HTTP error",
                request_id=getattr(request.state, "request_id", None),
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:  # pragma: no cover - defensive
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="INTERNAL_ERROR",
                message="Unexpected server error",
                request_id=getattr(request.state, "request_id", None),
            ),
        )

    return app


async def _initialize_cache_client(*, settings: Settings, observability: CacheObservability):
    valkey_settings = settings.valkey_settings
    if not valkey_settings.enabled:
        logger.info("VALKEY_URL not set; using in-memory cache stub")
        return InMemoryValkeyClient(default_ttl_seconds=valkey_settings.default_ttl_seconds)
    try:
        client = ValkeyAsyncClient.from_settings(
            valkey_settings,
            observability=observability,
        )
        sanitized = _sanitize_url(valkey_settings.url)
        logger.info("Valkey client initialized for %s", sanitized)
        return client
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Falling back to in-memory cache because Valkey init failed: %s", exc)
        return InMemoryValkeyClient(default_ttl_seconds=valkey_settings.default_ttl_seconds)


def _sanitize_url(raw: str | None) -> str:
    if not raw:
        return "<unset>"
    parsed = urlparse(raw)
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"
    sanitized = parsed._replace(netloc=netloc, username=None, password=None)
    return urlunparse(sanitized)


__all__ = ["create_app"]
