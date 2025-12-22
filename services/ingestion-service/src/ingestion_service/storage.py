"""S3 storage operations for document file persistence."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING
from uuid import UUID

import aioboto3

if TYPE_CHECKING:
    from ingestion_service.settings import Settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """Raised when storage operations fail."""


class S3Storage:
    """Async S3 client for storing and retrieving raw document files."""

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.raw_documents_bucket
        self._region = settings.aws_region
        self._endpoint_url = settings.aws_endpoint_url
        self._session = aioboto3.Session()

    def _s3_key(self, document_id: UUID, source_type: str) -> str:
        """Generate a unique S3 key for the document."""
        return f"documents/{document_id}.{source_type}"

    def _storage_uri(self, document_id: UUID, source_type: str) -> str:
        """Generate the S3 URI for the document."""
        key = self._s3_key(document_id, source_type)
        return f"s3://{self._bucket}/{key}"

    async def upload(
        self,
        *,
        document_id: UUID,
        file_bytes: bytes,
        source_type: str,
        content_type: str | None = None,
    ) -> tuple[str, str]:
        """
        Upload a file to S3.

        Returns:
            Tuple of (storage_uri, checksum)
        """
        key = self._s3_key(document_id, source_type)
        checksum = hashlib.md5(file_bytes).hexdigest()

        content_type_map = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "doc": "application/msword",
            "txt": "text/plain",
            "md": "text/markdown",
            "html": "text/html",
            "json": "application/json",
        }
        resolved_content_type = content_type or content_type_map.get(
            source_type, "application/octet-stream"
        )

        try:
            async with self._session.client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
            ) as s3:
                # Ensure bucket exists (for LocalStack / dev environments)
                try:
                    await s3.head_bucket(Bucket=self._bucket)
                except Exception:
                    logger.info("Creating bucket %s", self._bucket)
                    await s3.create_bucket(Bucket=self._bucket)

                await s3.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=file_bytes,
                    ContentType=resolved_content_type,
                    Metadata={
                        "document_id": str(document_id),
                        "source_type": source_type,
                        "checksum": checksum,
                    },
                )
            logger.info(
                "Uploaded document %s to s3://%s/%s (%d bytes)",
                document_id,
                self._bucket,
                key,
                len(file_bytes),
            )
            return self._storage_uri(document_id, source_type), checksum
        except Exception as exc:
            logger.exception("Failed to upload document %s to S3", document_id)
            raise StorageError(f"S3 upload failed: {exc}") from exc

    async def download(self, storage_uri: str) -> bytes:
        """
        Download a file from S3 by its storage URI.

        Args:
            storage_uri: S3 URI in format s3://bucket/key

        Returns:
            File bytes
        """
        if not storage_uri.startswith("s3://"):
            raise StorageError(f"Invalid storage URI: {storage_uri}")

        # Parse s3://bucket/key format
        uri_without_scheme = storage_uri[5:]  # Remove "s3://"
        parts = uri_without_scheme.split("/", 1)
        if len(parts) != 2:
            raise StorageError(f"Invalid storage URI format: {storage_uri}")
        bucket, key = parts

        try:
            async with self._session.client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
            ) as s3:
                response = await s3.get_object(Bucket=bucket, Key=key)
                body = await response["Body"].read()
                logger.info(
                    "Downloaded %d bytes from %s",
                    len(body),
                    storage_uri,
                )
                return body
        except Exception as exc:
            logger.exception("Failed to download from %s", storage_uri)
            raise StorageError(f"S3 download failed: {exc}") from exc

    async def delete(self, storage_uri: str) -> None:
        """
        Delete a file from S3.

        Args:
            storage_uri: S3 URI in format s3://bucket/key
        """
        if not storage_uri.startswith("s3://"):
            raise StorageError(f"Invalid storage URI: {storage_uri}")

        uri_without_scheme = storage_uri[5:]
        parts = uri_without_scheme.split("/", 1)
        if len(parts) != 2:
            raise StorageError(f"Invalid storage URI format: {storage_uri}")
        bucket, key = parts

        try:
            async with self._session.client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
            ) as s3:
                await s3.delete_object(Bucket=bucket, Key=key)
                logger.info("Deleted %s", storage_uri)
        except Exception as exc:
            logger.exception("Failed to delete %s", storage_uri)
            raise StorageError(f"S3 delete failed: {exc}") from exc

    async def get_download_url(
        self, storage_uri: str, expires_in: int = 3600
    ) -> str:
        """
        Generate a presigned URL for downloading a file.

        Args:
            storage_uri: S3 URI in format s3://bucket/key
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned download URL
        """
        if not storage_uri.startswith("s3://"):
            raise StorageError(f"Invalid storage URI: {storage_uri}")

        uri_without_scheme = storage_uri[5:]
        parts = uri_without_scheme.split("/", 1)
        if len(parts) != 2:
            raise StorageError(f"Invalid storage URI format: {storage_uri}")
        bucket, key = parts

        try:
            async with self._session.client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
            ) as s3:
                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=expires_in,
                )
                return url
        except Exception as exc:
            logger.exception("Failed to generate presigned URL for %s", storage_uri)
            raise StorageError(f"Presign generation failed: {exc}") from exc

