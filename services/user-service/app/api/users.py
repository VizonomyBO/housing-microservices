"""
FastAPI user endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.dependencies import DatabaseSession
from app.services.user_service import UserService
from app.utils.auth import UserContext, validate_token

logger = logging.getLogger(__name__)


class UserSelfUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=3)


class UserAdminUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    role: str | None = None
    status: str | None = None
    notes: str | None = None


class UserListRequest(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)
    roles: list[str] | None = None
    role: str | None = None
    statuses: list[str] | None = None
    status: str | None = None
    countries: list[str] | None = None
    country: str | None = None
    search: str | None = Field(default=None, min_length=1, max_length=200)


router = APIRouter(prefix="/v1/users", tags=["users"])


async def _require_user_context(request: Request) -> UserContext:
    """Validate token by calling auth-service and return user context."""
    from app.config import Config

    config = Config()
    return await validate_token(request, config.AUTH_SERVICE_URL)


def _require_admin(user: UserContext) -> None:
    roles = user.roles or []
    if "admin" not in [r.lower() for r in roles]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/me")
async def get_current_user(request: Request, session: DatabaseSession) -> JSONResponse:
    """Return the authenticated user's profile."""
    user_ctx = await _require_user_context(request)
    logger.info("Get current user request", extra={"user_id": user_ctx.user_id})

    user = UserService.get_user_by_id(session, user_ctx.user_id)
    if not user:
        logger.warning("User not found", extra={"user_id": user_ctx.user_id})
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    return JSONResponse({"user": user.to_dict()})


@router.put("/me")
@router.patch("/me")
async def update_current_user(
    request: Request, payload: UserSelfUpdate, session: DatabaseSession
) -> JSONResponse:
    """Update the authenticated user's profile."""
    user_ctx = await _require_user_context(request)
    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}

    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No valid fields to update")

    logger.info(
        "Updating user profile",
        extra={"user_id": user_ctx.user_id, "fields": list(update_data.keys())},
    )
    user, error = UserService.update_user(session, user_ctx.user_id, update_data, user_ctx.user_id)
    if error or not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error or "User not found")

    return JSONResponse(
        {"message": "Profile updated successfully", "user": user.to_dict()}, status_code=200
    )


@router.get("/search")
async def search_users(
    request: Request,
    session: DatabaseSession,
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
) -> JSONResponse:
    """Search users by email or name (admin only)."""
    user_ctx = await _require_user_context(request)
    _require_admin(user_ctx)

    logger.info(
        "User search request", extra={"admin_id": user_ctx.user_id, "query": q, "limit": limit}
    )
    users = UserService.search_users(session, q, limit)
    return JSONResponse({"users": [user.to_dict() for user in users], "count": len(users)})


@router.get("/{user_id}")
async def get_user(user_id: UUID, request: Request, session: DatabaseSession) -> JSONResponse:
    """Return a user profile by ID. Admins can view any user; others can only view themselves."""
    user_ctx = await _require_user_context(request)
    roles = user_ctx.roles or []
    if "admin" not in [r.lower() for r in roles] and user_ctx.user_id != str(user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

    logger.info(
        "Get user request",
        extra={"requested_user_id": str(user_id), "request_user_id": user_ctx.user_id},
    )
    user = UserService.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    include_sensitive = "admin" in [r.lower() for r in roles]
    return JSONResponse({"user": user.to_dict(include_sensitive=include_sensitive)})


@router.post("")
async def list_users(
    request: Request, session: DatabaseSession, payload: UserListRequest
) -> JSONResponse:
    """List users with pagination and filtering (admin only)."""
    user_ctx = await _require_user_context(request)
    _require_admin(user_ctx)

    logger.info(
        "List users request",
        extra={
            "admin_id": user_ctx.user_id,
            "page": payload.page,
            "per_page": payload.per_page,
            "roles": payload.roles,
            "statuses": payload.statuses,
            "countries": payload.countries,
            "search": payload.search,
        },
    )
    result = UserService.get_all_users(
        session,
        page=payload.page,
        per_page=payload.per_page,
        roles=(payload.roles or []) + ([payload.role] if payload.role else []),
        statuses=(payload.statuses or []) + ([payload.status] if payload.status else []),
        countries=(payload.countries or []) + ([payload.country] if payload.country else []),
        search=payload.search,
    )
    return JSONResponse(result)


@router.put("/{user_id}")
@router.patch("/{user_id}")
async def update_user(
    user_id: UUID, request: Request, payload: UserAdminUpdate, session: DatabaseSession
) -> JSONResponse:
    """Admin update endpoint."""
    user_ctx = await _require_user_context(request)
    _require_admin(user_ctx)

    update_data: dict[str, Any] = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None
    }
    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No valid fields to update")

    logger.info(
        "Admin updating user",
        extra={
            "admin_id": user_ctx.user_id,
            "target_user_id": str(user_id),
            "fields": list(update_data),
        },
    )
    user, error = UserService.update_user(session, user_id, update_data, user_ctx.user_id)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    return JSONResponse(
        {
            "message": "User updated successfully",
            "user": user.to_dict(include_sensitive=True),
        }
    )


@router.delete("/{user_id}")
async def delete_user(user_id: UUID, request: Request, session: DatabaseSession) -> JSONResponse:
    """Delete a user (admin only)."""
    user_ctx = await _require_user_context(request)
    _require_admin(user_ctx)

    if user_ctx.user_id == str(user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    success, error = UserService.delete_user(session, user_id)
    if not success:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error or "Delete failed")

    return JSONResponse({"message": "User deleted successfully"})
