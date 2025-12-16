"""Application factory for the Agent API FastAPI service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from shared_data_layer.db.session import DatabaseSessionManager
from starlette.middleware.cors import CORSMiddleware

from agent_api.auth import AuthTokenValidator
from agent_api.aws.factory import AWSClientFactory
from agent_api.http.deps import UnconfiguredChatRunner, get_chat_runner, set_chat_runner
from agent_api.http.errors import GatewayError, error_payload
from agent_api.http.rate_limit import BypassRateLimiter, RateLimiterProtocol
from agent_api.http.routes.attachments import router as attachments_router
from agent_api.http.routes.chat import router as chat_router
from agent_api.http.routes.conversations import router as conversations_router
from agent_api.http.routes.demo import router as demo_router
from agent_api.http.routes.documents import router as documents_router
from agent_api.http.routes.metrics import router as metrics_router
from agent_api.http.routes.pillars import router as pillars_router
from agent_api.settings import Settings, load_settings
from cache import InMemoryValkeyClient, ValkeyAsyncClient, ValkeyCacheClientProtocol
from nodes.retrieval.utils.language import LinguaLanguageDetector, StubLanguageDetector
from services.langgraph_runner import LangGraphChatRunner
from services.model_clients import (
    OpenAIChatClient,
    VoyageEmbeddingClient,
    VoyageRerankClient,
)
from telemetry import CacheObservability, get_metrics_registry

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = load_settings()
    if settings.reduced_scope.real_tooling_mode():
        logger.info("Reduced scope real tooling mode enabled; real dependencies are required")
    elif settings.reduced_scope.is_enabled():
        logger.info(
            "Reduced scope text-only mode enabled; cache/rate limit bypasses must be explicitly allowed"
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        registry = get_metrics_registry()
        app.state.metrics_registry = registry
        app.state.auth_validator = AuthTokenValidator(settings.auth, metrics=registry)
        app.state.cache_observability = CacheObservability(
            metrics=registry, namespace=settings.metrics_namespace
        )
        app.state.settings = settings

        app.state.reduced_scope = settings.reduced_scope
        app.state.rate_limiter = _build_rate_limiter(settings)
        app.state.aws_factory = AWSClientFactory(settings=settings)

        app.state.valkey_client = await _initialize_cache_client(
            settings=settings,
            observability=app.state.cache_observability,
        )

        language_detector = _build_language_detector(settings=settings)
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required; no fallback chat model is available.")
        if not settings.voyage_api_key:
            raise RuntimeError("VOYAGE_API_KEY is required; embedding and rerank clients have no fallback.")
        openai_client = OpenAIChatClient(
            api_key=settings.openai_api_key,
            model=settings.openai_chat_model,
        )
        voyage_client = VoyageEmbeddingClient(
            api_key=settings.voyage_api_key,
            model=settings.voyage_embedding_model,
        )
        voyage_reranker = VoyageRerankClient(
            api_key=settings.voyage_api_key,
            model=settings.voyage_rerank_model,
        )

        runner = LangGraphChatRunner(
            cache_client=app.state.valkey_client,
            cache_observability=app.state.cache_observability,
            language_detector=language_detector,
            openai_client=openai_client,
            metrics=registry,
            retrieval_embedding_client=voyage_client,
            retrieval_reranker=voyage_reranker,
        )
        if isinstance(get_chat_runner(), UnconfiguredChatRunner):
            set_chat_runner(runner)

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

    cors_allowed_origins = list(settings.cors_allowed_origins) or ["*"]
    cors_allow_credentials = settings.cors_allow_credentials
    if "*" in cors_allowed_origins and cors_allow_credentials:
        cors_allow_credentials = False
        logger.info("Wildcard CORS origins detected; disabling credentials for compatibility.")

    cors_middleware_cls: Any = CORSMiddleware
    app.add_middleware(
        cors_middleware_cls,  # type: ignore[arg-type]
        allow_origins=cors_allowed_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def inject_request_id(request: Request, call_next):
        request_id = request.headers.get("Viz-Request-Id") or f"viz-{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["Viz-Request-Id"] = request_id
        return response

    app.include_router(chat_router)
    app.include_router(documents_router)
    app.include_router(conversations_router)
    app.include_router(attachments_router)
    app.include_router(demo_router)
    app.include_router(pillars_router)
    app.include_router(metrics_router)

    @app.get("/health", include_in_schema=False)
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health", include_in_schema=False)
    async def versioned_health() -> dict[str, str]:
        return {"status": "ok"}

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
        logger.exception("Unhandled exception in request", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="INTERNAL_ERROR",
                message="Unexpected server error",
                request_id=getattr(request.state, "request_id", None),
            ),
        )

    return app


async def _initialize_cache_client(
    *, settings: Settings, observability: CacheObservability
) -> ValkeyCacheClientProtocol:
    valkey_settings = settings.valkey_settings
    if not valkey_settings.enabled:
        if settings.allow_in_memory_valkey:
            logger.warning(
                "VALKEY_URL not set; using in-memory cache only because ALLOW_IN_MEMORY_VALKEY=1"
            )
            return InMemoryValkeyClient(default_ttl_seconds=valkey_settings.default_ttl_seconds)
        raise RuntimeError(
            "VALKEY_URL is required for cache operations. Set ALLOW_IN_MEMORY_VALKEY=1 only for "
            "tests/dev when an in-memory cache is acceptable."
        )
    client = ValkeyAsyncClient.from_settings(
        valkey_settings,
        observability=observability,
    )
    sanitized = _sanitize_url(valkey_settings.url)
    logger.info("Valkey client initialized for %s", sanitized)
    return client


def _sanitize_url(raw: str | None) -> str:
    if not raw:
        return "<unset>"
    parsed = urlparse(raw)
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"
    sanitized = parsed._replace(netloc=netloc, username=None, password=None)
    return urlunparse(sanitized)


def _build_rate_limiter(settings: Settings) -> RateLimiterProtocol:
    if settings.allow_rate_limiter_bypass:
        logger.warning("Rate limiter bypass enabled via ALLOW_RATE_LIMITER_BYPASS=1")
        return BypassRateLimiter()
    raise RuntimeError(
        "Rate limiter backend is not configured; set ALLOW_RATE_LIMITER_BYPASS=1 only for "
        "tests/dev or provide a real limiter implementation."
    )


def _build_language_detector(*, settings: Settings):
    try:
        return LinguaLanguageDetector()
    except RuntimeError as exc:
        if settings.allow_stub_language_detector:
            logger.warning(
                "Lingua language detector unavailable; using stub because "
                "ALLOW_STUB_LANGUAGE_DETECTOR=1"
            )
            return StubLanguageDetector(language_code="en", confidence=1.0)
        raise RuntimeError("Lingua language detector is required but unavailable") from exc


__all__ = ["create_app"]
