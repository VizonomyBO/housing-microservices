"""
FastAPI application for the auth-service.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import auth, system
from app.api.auth import limiter
from app.config import Config
from app.database import create_tables, init_db
from app.middleware import AuthMiddleware


def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle rate limit exceeded exceptions"""
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


def _create_cors_kwargs(config: Config) -> dict[str, object]:
    """Create CORS middleware configuration"""
    origins: list[str] = (
        config.CORS_ORIGINS if isinstance(config.CORS_ORIGINS, list) else [str(config.CORS_ORIGINS)]
    )
    return {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
        "expose_headers": ["Authorization", "Content-Type"],
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    config_obj = app.state.config
    init_db(config_obj)
    create_tables()
    yield
    # Shutdown - cleanup if needed


def create_api_app(config_class: type[Config] = Config) -> FastAPI:
    """
    Build a FastAPI instance wired up with the auth middleware.
    """
    config_obj = config_class()
    title = config_obj.APP_NAME.replace("-", " ").title()

    fastapi_app = FastAPI(
        title=title,
        version=config_obj.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    fastapi_app.state.config = config_obj

    # Initialize rate limiter
    fastapi_app.state.limiter = limiter
    fastapi_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    fastapi_app.add_middleware(SlowAPIMiddleware)

    # Add CORS middleware
    cors_kwargs = _create_cors_kwargs(config_obj)
    fastapi_app.add_middleware(CORSMiddleware, **cors_kwargs)

    # Add authentication middleware
    # This will protect all /v1/* routes EXCEPT public paths defined in middleware
    fastapi_app.add_middleware(
        AuthMiddleware,
        auth_service_url=os.getenv("AUTH_SERVICE_URL", "http://localhost:5001"),
        mock_validation=getattr(config_obj, "TESTING", False),
        use_direct_validation=True,  # Use direct validation since we're in the same service
    )

    # Include routers
    fastapi_app.include_router(auth.router)
    fastapi_app.include_router(system.router)

    return fastapi_app


app = create_api_app()
