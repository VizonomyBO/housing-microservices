"""
System endpoints for health checks and API documentation
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import Config
from app.dependencies import DatabaseSession

router = APIRouter(tags=["System"])
config = Config()


@router.get("/health")
async def health_check(request: Request, session: DatabaseSession) -> JSONResponse:
    """
    Health check endpoint.
    Check if the service is running and healthy.
    """
    # Check database connection
    try:
        session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    overall_status = "healthy" if db_status == "connected" else "degraded"
    status_code = (
        status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return JSONResponse(
        {
            "status": overall_status,
            "timestamp": datetime.now(UTC).isoformat(),
            "service": config.APP_NAME,
            "version": config.APP_VERSION,
            "database": db_status,
        },
        status_code=status_code,
    )


@router.get("/status")
async def service_status(request: Request) -> JSONResponse:
    """
    Service status endpoint with detailed information.
    """
    return JSONResponse(
        {
            "service": config.APP_NAME,
            "version": config.APP_VERSION,
            "timestamp": datetime.now(UTC).isoformat(),
            "endpoints": {
                "health": "/health",
                "status": "/status",
                "openapi": "/openapi.json",
                "auth": "/v1/auth/*",
            },
        }
    )
