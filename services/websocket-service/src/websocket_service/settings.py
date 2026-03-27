from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "websocket-service"
    app_port: int = Field(default=8091)
    database_url: str = Field(..., description="Async SQLAlchemy database URL")
    auth_shared_secret: str | None = Field(default=None, alias="AUTH_SHARED_SECRET")
    jwt_secret_key: str | None = Field(default=None, alias="JWT_SECRET_KEY")
    websocket_poll_interval_seconds: float = Field(default=2.0)

    @property
    def token_secret(self) -> str | None:
        return self.auth_shared_secret or self.jwt_secret_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
