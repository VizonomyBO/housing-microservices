"""
FastAPI application for the user-service.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import system, users
from app.config import Config
from app.db import create_tables, init_db


def _create_cors_kwargs(config: Config) -> dict[str, object]:
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
    Build a FastAPI instance wired up with the shared auth middleware.
    """

    config_obj = config_class()
    title = config_obj.SERVICE_NAME.replace("-", " ").title()

    fastapi_app = FastAPI(
        title=title,
        version=config_obj.SERVICE_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    fastapi_app.state.config = config_obj

    cors_kwargs = _create_cors_kwargs(config_obj)
    fastapi_app.add_middleware(cast(Any, CORSMiddleware), **cors_kwargs)

    fastapi_app.include_router(system.router)
    fastapi_app.include_router(users.router)

    return fastapi_app


app = create_api_app()
