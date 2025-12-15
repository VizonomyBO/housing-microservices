"""
Configuration settings for the Account Service
"""

import os
from datetime import timedelta


class Config:
    """Base configuration"""

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql://account_user:secure_password@localhost:5432/account_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
    }

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 900)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 2592000))
    )

    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32))
    # Cookie security: Set to False in development when HTTPS is not available
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "True").lower() == "true"

    # CORS
    # Default includes common local frontends (localhost:3000, localhost:5173) plus "*"
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,*",
    ).split(",")

    # Rate Limiting
    RATELIMIT_STORAGE_URL = "memory://"

    # Email (for password reset)
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    SES_REGION = os.getenv("SES_REGION", AWS_REGION)
    SES_SOURCE_EMAIL = os.getenv("SES_SOURCE_EMAIL", os.getenv("EMAIL_FROM", "addis@vizonomy.com"))
    SES_CONFIGURATION_SET = os.getenv("SES_CONFIGURATION_SET", "")
    PASSWORD_RESET_URL = os.getenv("PASSWORD_RESET_URL", "https://app.vizonomy.com/reset-password")

    # Application
    APP_NAME = "Account Management Service"
    APP_VERSION = "1.0.0"
    SERVICE_NAME = "auth-service"
    SERVICE_VERSION = "1.0.0"
