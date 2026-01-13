"""S3 storage client for document downloads and uploads."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

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


def upload_pdf_to_s3(
    file_bytes: bytes,
    document_id: str | UUID,
    document_name: str,
    settings: Settings,
) -> str:
    """
    Upload a PDF file to S3 housing-pdf-docs bucket.

    Args:
        file_bytes: The file content as bytes
        document_id: The document UUID as string or UUID
        document_name: The original document name
        settings: Application settings

    Returns:
        S3 URI of the uploaded file (e.g., s3://housing-pdf-docs/document_id/filename.pdf)

    Raises:
        ValueError: If S3 bucket is not configured
        RuntimeError: If upload fails
    """
    if not settings.s3_housing_pdf_bucket:
        raise ValueError("S3 housing PDF bucket is not configured")

    bucket_name = settings.s3_housing_pdf_bucket
    region = settings.aws_region

    # Convert document_id to string if it's a UUID
    doc_id_str = str(document_id)

    # Create S3 key: document_id/filename
    # Use document_id as prefix for organization
    s3_key = f"{doc_id_str}/{document_name}"

    # Build boto3 client configuration
    client_kwargs = {"region_name": region}

    if settings.s3_endpoint_url:
        client_kwargs["endpoint_url"] = settings.s3_endpoint_url

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    try:
        # Initialize S3 client
        s3_client = boto3.client("s3", **client_kwargs)

        # Upload file
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_bytes,
            ContentType="application/pdf",
            ServerSideEncryption="AES256",
        )

        s3_uri = f"s3://{bucket_name}/{s3_key}"
        logger.info(
            "Uploaded PDF to S3: %s (size: %d bytes)",
            s3_uri,
            len(file_bytes),
        )
        return s3_uri

    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        logger.error(
            "S3 upload failed: %s - %s (bucket: %s, key: %s)",
            error_code,
            error_message,
            bucket_name,
            s3_key,
        )
        raise RuntimeError(
            f"S3 upload failed: {error_code} - {error_message}"
        ) from exc
    except BotoCoreError as exc:
        logger.error("S3 client error: %s", exc)
        raise RuntimeError(f"S3 client error: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error during S3 upload")
        raise RuntimeError(f"Unexpected S3 upload error: {exc}") from exc

