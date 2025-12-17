"""
FastAPI dependencies for database sessions
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_session


def get_db() -> Generator[Session]:
    """Get a database session with proper cleanup"""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


# Type alias for dependency injection
DatabaseSession = Annotated[Session, Depends(get_db)]
