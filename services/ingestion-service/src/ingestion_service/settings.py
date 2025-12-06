from __future__ import annotations

from functools import lru_cache
from typing import Any, Sequence

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration for the ingestion service."""

    app_name: str = "ingestion-service"
    app_port: int = Field(default=8085, description="Port for uvicorn")
    database_url: str = Field(..., description="Async SQLAlchemy database URL")

    # Auth/token validation
    jwt_secret_key: str | None = Field(default=None, description="JWT secret for access tokens")
    auth_base_url: AnyUrl | None = Field(
        default=None, description="Auth service base URL for token verification fallback"
    )
    auth_verify_path: str = Field(default="/v1/auth/verify-token")

    # Upload signing
    signing_secret: str | None = Field(default=None, description="Secret used to sign upload fields")
    upload_ttl_seconds: int = Field(default=900, description="Presign validity window")
    max_file_size_bytes: int = Field(default=100 * 1024 * 1024, description="Upload size cap (100MB)")

    # Ingestion
    allowed_source_types: Sequence[str] = Field(
        default=(
            "pdf",
            "docx",
            "doc",
            "txt",
            "md",
            "html",
            "csv",
            "xlsx",
            "json",
        )
    )
    voyage_api_key: str | None = None
    voyage_model: str = "voyage-3"
    worker_name: str = "ingestion-service"

    class Config:
        env_file = ".env.active"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def model_post_init(self, __context: Any) -> None:  # type: ignore[override]
        if self.signing_secret is None and self.jwt_secret_key:
            object.__setattr__(self, "signing_secret", self.jwt_secret_key)
        elif self.signing_secret is None:
            import secrets

            object.__setattr__(self, "signing_secret", secrets.token_urlsafe(32))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
