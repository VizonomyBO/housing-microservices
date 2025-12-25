"""S3 storage client for document downloads."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from agent_api.settings import Settings

logger = logging.getLogger(__name__)


class S3StorageClient:
    """Client for generating presigned download URLs for documents."""

    def __init__(self, settings: Settings) -> None:
        """Initialize S3 client with settings."""
        self._bucket_name = settings.s3_bucket_name
        self._region = settings.s3_region

        # Build boto3 client configuration
        client_kwargs = {"region_name": self._region}

        if settings.s3_endpoint_url:
            client_kwargs["endpoint_url"] = settings.s3_endpoint_url

        if settings.aws_access_key_id and settings.aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

        self._s3_client = boto3.client("s3", **client_kwargs)

    def generate_download_url(self, *, storage_uri: str, expires_in: int = 3600) -> str:
        """
        Generate presigned download URL for a document.

        Args:
            storage_uri: S3 URI in format s3://bucket/key
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL for downloading the document
        """
        if not storage_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {storage_uri}")

        # Parse bucket and key from URI
        parts = storage_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI format: {storage_uri}")

        bucket, key = parts

        try:
            url = self._s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            logger.debug("Generated presigned URL for %s", storage_uri)
            return url
        except ClientError as exc:
            logger.exception("Failed to generate presigned URL for %s", storage_uri)
            raise RuntimeError(f"Failed to generate download URL: {exc}") from exc

