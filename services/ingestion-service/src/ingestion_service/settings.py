from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Sequence

from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared_data_layer.config import (
    EMBEDDING_DIMENSION,
    DEFAULT_VOYAGE_EMBEDDING_DIMENSION,
)

ALLOWED_VOYAGE_OUTPUT_DIMENSIONS: tuple[int, ...] = (256, 512, 1024, 2048)


class Settings(BaseSettings):
    """Runtime configuration for the ingestion service."""

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "ingestion-service"
    app_port: int = Field(default=8085, description="Port for uvicorn")
    database_url: str = Field(..., description="Async SQLAlchemy database URL")

    # Auth/token validation
    jwt_secret_key: str | None = Field(
        default=None, description="JWT secret for access tokens"
    )
    auth_base_url: AnyUrl | None = Field(
        default=None,
        description="Auth service base URL for token verification fallback",
    )
    auth_verify_path: str = Field(default="/v1/auth/verify-token")

    # Upload signing
    signing_secret: str | None = Field(
        default=None, description="Secret used to sign upload fields"
    )
    upload_ttl_seconds: int = Field(default=900, description="Presign validity window")
    max_file_size_bytes: int = Field(
        default=100 * 1024 * 1024, description="Upload size cap (100MB)"
    )

    # Ingestion
    allowed_source_types: Sequence[str] = Field(
        default=("pdf", "docx", "doc", "txt", "md", "html", "json")
    )
    voyage_api_key: str | None = None
    voyage_model: str = "voyage-context-3"
    voyage_output_dimension: int = Field(
        default=DEFAULT_VOYAGE_EMBEDDING_DIMENSION,
        description="voyage-context-3 output dimension; must align with pgvector column dimension",
    )
    vector_store_dimension: int = Field(
        default=EMBEDDING_DIMENSION,
        description="pgvector storage dimension derived from shared data layer config",
    )
    worker_name: str = "ingestion-service"

    def model_post_init(self, __context: Any) -> None:  # type: ignore[override]
        if self.signing_secret is None and self.jwt_secret_key:
            object.__setattr__(self, "signing_secret", self.jwt_secret_key)
        elif self.signing_secret is None:
            import secrets

            object.__setattr__(self, "signing_secret", secrets.token_urlsafe(32))

    @field_validator("voyage_output_dimension", mode="before")
    @classmethod
    def _validate_output_dimension(cls, value: Any) -> int:
        if value is None:
            return DEFAULT_VOYAGE_EMBEDDING_DIMENSION
        try:
            dimension = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("voyage_output_dimension must be an integer") from exc
        if dimension not in ALLOWED_VOYAGE_OUTPUT_DIMENSIONS:
            raise ValueError(
                f"voyage_output_dimension must be one of {ALLOWED_VOYAGE_OUTPUT_DIMENSIONS}, "
                f"got {dimension}"
            )
        return dimension

    @field_validator("vector_store_dimension", mode="before")
    @classmethod
    def _validate_vector_dimension(cls, value: Any) -> int:
        if value is None:
            return EMBEDDING_DIMENSION
        try:
            dimension = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("vector_store_dimension must be an integer") from exc
        if dimension <= 0:
            raise ValueError("vector_store_dimension must be positive")
        return dimension


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
