"""S3 storage client for original document files."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from ingestion_service.settings import Settings

logger = logging.getLogger(__name__)


class S3StorageClient:
    """Client for storing and retrieving original documents from S3."""

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

    def upload_document(
        self,
        *,
        document_id: UUID,
        file_bytes: bytes,
        content_type: str,
        source_type: str,
        filename: str | None = None,
    ) -> str:
        """
        Upload original document to S3.

        Args:
            document_id: The UUID of the document
            file_bytes: The raw file bytes
            content_type: MIME type of the file
            source_type: File extension (pdf, docx, etc.)
            filename: Original filename; used as S3 key leaf so download-by-name can find it

        Returns:
            S3 URI in format s3://bucket/key
        """
        if not self._bucket_name:
            raise ValueError("S3 bucket name not configured")

        leaf = filename if filename else f"source.{source_type}"
        key = f"raw/documents/{document_id}/{leaf}"

        try:
            self._s3_client.put_object(
                Bucket=self._bucket_name,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
                Metadata={
                    "document_id": str(document_id),
                    "source_type": source_type,
                },
            )
            logger.info(
                "Uploaded document %s to S3: %s/%s",
                document_id,
                self._bucket_name,
                key,
            )
        except ClientError as exc:
            logger.exception("Failed to upload document %s to S3", document_id)
            raise RuntimeError(f"S3 upload failed: {exc}") from exc

        return f"s3://{self._bucket_name}/{key}"

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

    def delete_document(self, *, storage_uri: str) -> None:
        """
        Delete document from S3.

        Args:
            storage_uri: S3 URI in format s3://bucket/key
        """
        if not storage_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {storage_uri}")

        parts = storage_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI format: {storage_uri}")

        bucket, key = parts

        try:
            self._s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info("Deleted document from S3: %s", storage_uri)
        except ClientError as exc:
            logger.exception("Failed to delete document from S3: %s", storage_uri)
            raise RuntimeError(f"S3 delete failed: {exc}") from exc

    def download_document(self, *, storage_uri: str) -> bytes:
        if not storage_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {storage_uri}")

        parts = storage_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI format: {storage_uri}")

        bucket, key = parts
        try:
            response = self._s3_client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except ClientError as exc:
            logger.exception("Failed to download document from S3: %s", storage_uri)
            raise RuntimeError(f"S3 download failed: {exc}") from exc
