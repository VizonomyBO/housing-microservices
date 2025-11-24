"""
Authentication and context middleware for FastAPI
"""

from app.middleware.auth_middleware import AuthMiddleware, UserContext

__all__ = ["AuthMiddleware", "UserContext"]
