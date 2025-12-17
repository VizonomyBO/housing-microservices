"""
Application configuration
"""

import os
from datetime import timedelta


class Config:
    """Base configuration"""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"

    # Database
    _db_name = os.getenv("AUTH_DB", "auth_db")
    _db_user = os.getenv("POSTGRES_USER", "vizonomy_user")
    _db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    _db_host = os.getenv("POSTGRES_HOST", "localhost")
    _db_port = os.getenv("POSTGRES_PORT", "5432")
    SQLALCHEMY_DATABASE_URI = (
        os.getenv("AUTH_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or f"postgresql://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "15"))
    )

    # Auth Service Configuration
    AUTH_SERVICE_URL = (
        os.getenv("AUTH_INTERNAL_BASE_URL")
        or os.getenv("AUTH_BASE_URL")
        or os.getenv("AUTH_SERVICE_URL", "http://localhost:5001")
    )

    # CORS
    # Default includes common local frontends (localhost:3000, localhost:5173) plus "*"
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,*",
    ).split(",")

    # Service Info
    SERVICE_NAME = "user-service"
    SERVICE_VERSION = "1.0.0"


class TestConfig(Config):
    """Testing configuration"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test-secret-key"
    AUTH_SERVICE_URL = "http://localhost:5001"
