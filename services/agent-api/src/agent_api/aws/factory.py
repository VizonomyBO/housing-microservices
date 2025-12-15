"""AWS helper utilities used by the Agent API."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config

from agent_api.settings import Settings


class AWSClientFactory:
    """Creates boto3 clients that honor the service's LocalStack toggles."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._session = boto3.session.Session(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

    @property
    def endpoint_url(self) -> str | None:
        return self._settings.aws_endpoint_url

    def client(
        self,
        service_name: str,
        *,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        config: Config | None = None,
        **kwargs: Any,
    ):
        resolved_endpoint = endpoint_url
        if resolved_endpoint is None:
            resolved_endpoint = self._settings.aws_endpoint_url
        return self._session.client(
            service_name,
            region_name=region_name or self._settings.aws_region,
            endpoint_url=resolved_endpoint,
            config=config,
            **kwargs,
        )


__all__ = ["AWSClientFactory"]
