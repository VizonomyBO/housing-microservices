"""Prometheus metrics endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from prometheus_client import REGISTRY, generate_latest

from agent_api.http.deps import get_settings

router = APIRouter(tags=["metrics"])


async def _verify_metrics_auth(request: Request) -> None:
    settings = get_settings(request)
    expected = settings.metrics_auth_token
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="METRICS_AUTH_TOKEN is not configured",
        )
    header_value = request.headers.get(settings.metrics_auth_header)
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {settings.metrics_auth_header} header",
        )
    token = header_value
    scheme = settings.metrics_auth_scheme.strip()
    if scheme:
        prefix = f"{scheme} "
        if not header_value.startswith(prefix):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Expected {settings.metrics_auth_header} to start with '{scheme} '",
            )
        token = header_value[len(prefix) :]
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid metrics auth token",
        )


@router.get("/metrics", summary="Prometheus scrape endpoint")
async def get_metrics(
    _: Annotated[None, Depends(_verify_metrics_auth)],
) -> Response:
    payload = generate_latest(REGISTRY)
    headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
        headers=headers,
    )


__all__ = ["router"]
