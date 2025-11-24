"""
System endpoints exposed via FastAPI.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import Config
from app.dependencies import DatabaseSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["system"])
config = Config()


@router.get("/health")
async def health_check(session: DatabaseSession) -> JSONResponse:
    """Basic health probe including database connectivity."""

    try:
        session.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Database health check failed", extra={"error": str(exc)})
        db_status = f"unhealthy: {exc!s}"

    overall_status = "healthy" if db_status == "healthy" else "unhealthy"
    status_code = (
        status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    payload = {
        "status": overall_status,
        "service": config.SERVICE_NAME,
        "version": config.SERVICE_VERSION,
        "database": db_status,
    }
    return JSONResponse(payload, status_code=status_code)


@router.get("/")
async def index() -> JSONResponse:
    """Service metadata endpoint."""

    payload = {
        "service": config.SERVICE_NAME,
        "version": config.SERVICE_VERSION,
        "description": "User profile management service",
        "endpoints": {
            "health": "/v1/health",
            "current_user": "/v1/users/me",
            "users": "/v1/users",
        },
    }
    return JSONResponse(payload)
