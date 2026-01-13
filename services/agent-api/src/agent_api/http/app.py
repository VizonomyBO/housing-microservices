"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from shared_data_layer.db.session import DatabaseSessionManager
from starlette.middleware.cors import CORSMiddleware

from agent_api.agent.runner import LangGraphRunner
from agent_api.auth.validator import AuthTokenValidator
from agent_api.http.deps import (
    UnconfiguredRunner,
    get_runner,
    set_chat_runner,
)
from agent_api.http.errors import GatewayError, error_payload
from agent_api.http.routes.attachments import router as attachments_router
from agent_api.http.routes.chat import router as chat_router
from agent_api.http.routes.conversations import router as conversations_router
from agent_api.http.routes.documents import router as documents_router
from agent_api.http.routes.metrics import router as metrics_router
from agent_api.http.routes.reports import router as reports_router
from agent_api.services.preprocessing import run_preprocessing
from agent_api.settings import load_settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        print("=" * 80)
        print("LIFESPAN STARTUP BEGINNING")
        print("=" * 80)
        app.state.settings = settings
        app.state.auth_validator = AuthTokenValidator(settings.auth)

        db_initialized = False
        print(
            f"Initializing database with URL: {settings.database_url[:50] if settings.database_url else 'None'}..."
        )
        logger.info(
            f"Initializing database with URL: {settings.database_url[:50] if settings.database_url else 'None'}..."
        )
        if settings.database_url:
            DatabaseSessionManager.init(settings.database_url)
            db_initialized = True
            logger.info("Database initialized successfully")
        else:  # pragma: no cover
            logger.warning("DATABASE_URL not configured; database-backed operations are disabled")
        app.state.db_initialized = db_initialized

        runner = LangGraphRunner(settings=settings)
        if isinstance(get_runner(), UnconfiguredRunner):
            set_chat_runner(runner)

        # Launch cache preprocessing if enabled
        preprocessing_task = None
        print(
            f"Preprocessing check: preprocess_cache_on_startup={settings.preprocess_cache_on_startup}, db_initialized={db_initialized}"
        )
        logger.info(
            f"Preprocessing check: preprocess_cache_on_startup={settings.preprocess_cache_on_startup}, db_initialized={db_initialized}"
        )

        async def run_preprocessing_with_error_handling():
            try:
                print("About to call run_preprocessing...")
                await run_preprocessing(runner)
                print("run_preprocessing completed")
            except Exception as e:
                print(f"ERROR in preprocessing background task: {e}")
                import traceback

                traceback.print_exc()
                logger.error(f"Error in preprocessing background task: {e}", exc_info=True)

        if settings.preprocess_cache_on_startup and db_initialized:
            print("Cache preprocessing enabled - launching background task")
            logger.info("Cache preprocessing enabled - launching background task")
            try:
                preprocessing_task = asyncio.create_task(run_preprocessing_with_error_handling())
                print("Preprocessing task created successfully")
                logger.info("Preprocessing task created successfully")
            except Exception as e:
                print(f"ERROR: Failed to create preprocessing task: {e}")
                logger.error(f"Failed to create preprocessing task: {e}", exc_info=True)
        elif settings.preprocess_cache_on_startup:
            logger.warning("Cache preprocessing enabled but DB not initialized")
        else:
            logger.info("Cache preprocessing is disabled (PREPROCESS_CACHE_ON_STARTUP=false)")

        try:
            yield
        finally:
            if preprocessing_task:
                if not preprocessing_task.done():
                    logger.info("Cancelling preprocessing task...")
                    preprocessing_task.cancel()
                    try:
                        await preprocessing_task
                    except asyncio.CancelledError:
                        pass
            if db_initialized:
                await DatabaseSessionManager.dispose()

    app = FastAPI(
        title="Agent API",
        version="0.3.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    cors_allowed_origins = list(settings.cors_allowed_origins) or ["*"]
    cors_allow_credentials = settings.cors_allow_credentials
    if "*" in cors_allowed_origins and cors_allow_credentials:
        cors_allow_credentials = False
        logger.info("Wildcard CORS origins detected; disabling credentials for compatibility.")

    app.add_middleware(
        cast(Any, CORSMiddleware),
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
    app.include_router(metrics_router)
    app.include_router(reports_router)

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
    ) -> JSONResponse:  # pragma: no cover
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


__all__ = ["create_app"]
