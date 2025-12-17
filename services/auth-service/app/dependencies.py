"""
FastAPI dependencies for database sessions and authentication
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.middleware import UserContext


def get_db() -> Generator[Session]:
    """Get a database session with proper cleanup"""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


# Type alias for dependency injection
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_user_context(request: Request) -> UserContext:
    """Get user context from request state (injected by AuthMiddleware)"""
    user: UserContext | None = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication context",
        )
    return user


# Type alias for authenticated endpoints
AuthenticatedUser = Annotated[UserContext, Depends(get_user_context)]
