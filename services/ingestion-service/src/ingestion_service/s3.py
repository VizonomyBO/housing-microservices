"""S3 upload utilities for document storage."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from ingestion_service.settings import Settings

logger = logging.getLogger(__name__)


def upload_pdf_to_s3(
    file_bytes: bytes,
    document_id: str,
    document_name: str,
    settings: Settings,
) -> str:
    """
    Upload a PDF file to S3 housing-pdf-docs bucket.

    Args:
        file_bytes: The file content as bytes
        document_id: The document UUID as string
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

    # Create S3 key: document_id/filename
    # Use document_id as prefix for organization
    s3_key = f"{document_id}/{document_name}"

    try:
        # Initialize S3 client
        s3_client = boto3.client("s3", region_name=region)

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


def download_pdf_from_s3(
    document_id: str,
    document_name: str,
    settings: Settings,
) -> bytes:
    """
    Download a PDF file from S3 housing-pdf-docs bucket.

    Tries multiple filename variations to handle cases where the extension
    might be missing or different.

    Args:
        document_id: The document UUID as string
        document_name: The original document name (may or may not have .pdf extension)
        settings: Application settings

    Returns:
        The file content as bytes

    Raises:
        ValueError: If S3 bucket is not configured
        RuntimeError: If download fails (file not found, etc.)
    """
    if not settings.s3_housing_pdf_bucket:
        raise ValueError("S3 housing PDF bucket is not configured")

    bucket_name = settings.s3_housing_pdf_bucket
    region = settings.aws_region

    # Try multiple filename variations
    # 1. document_name as-is
    # 2. document_name with .pdf extension
    # 3. List objects and use the first one found
    filename_variations = [
        document_name,
        f"{document_name}.pdf" if not document_name.endswith(".pdf") else None,
    ]
    filename_variations = [f for f in filename_variations if f is not None]

    s3_client = boto3.client("s3", region_name=region)
    last_exc: Exception | None = None

    # Try each filename variation
    for filename in filename_variations:
        s3_key = f"{document_id}/{filename}"
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            file_bytes = response["Body"].read()

            logger.info(
                "Downloaded PDF from S3: s3://%s/%s (size: %d bytes)",
                bucket_name,
                s3_key,
                len(file_bytes),
            )
            return file_bytes

        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                last_exc = exc
                continue  # Try next variation
            # Other errors should be raised immediately
            error_message = exc.response.get("Error", {}).get("Message", str(exc))
            logger.error(
                "S3 download failed: %s - %s (bucket: %s, key: %s)",
                error_code,
                error_message,
                bucket_name,
                s3_key,
            )
            raise RuntimeError(
                f"S3 download failed: {error_code} - {error_message}"
            ) from exc

    # If all variations failed, try listing objects with the document_id prefix
    try:
        prefix = f"{document_id}/"
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, MaxKeys=1)
        
        if "Contents" in response and len(response["Contents"]) > 0:
            # Use the first object found
            s3_key = response["Contents"][0]["Key"]
            response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            file_bytes = response["Body"].read()

            logger.info(
                "Downloaded PDF from S3 (found via listing): s3://%s/%s (size: %d bytes)",
                bucket_name,
                s3_key,
                len(file_bytes),
            )
            return file_bytes
    except Exception as exc:
        logger.warning("Failed to list S3 objects as fallback: %s", exc)

    # All attempts failed
    if last_exc:
        logger.warning(
            "PDF not found in S3: s3://%s/%s/* (tried variations: %s)",
            bucket_name,
            f"{document_id}/",
            ", ".join(filename_variations),
        )
        raise RuntimeError(f"PDF not found: {document_name}") from last_exc

    raise RuntimeError(f"PDF not found: {document_name}")


def find_and_download_pdf_by_name(
    canonical_name: str,
    settings: Settings,
) -> bytes:
    """
    Search S3 across all folders to find and download a PDF by canonical name.
    
    Searches through all objects in the bucket to find the first one where
    the filename matches the canonical_name (with or without .pdf extension).
    
    Args:
        canonical_name: The canonical document name to search for
        settings: Application settings
        
    Returns:
        The file content as bytes
        
    Raises:
        ValueError: If S3 bucket is not configured
        RuntimeError: If document not found or download fails
    """
    if not settings.s3_housing_pdf_bucket:
        raise ValueError("S3 housing PDF bucket is not configured")
    
    bucket_name = settings.s3_housing_pdf_bucket
    region = settings.aws_region
    
    # Normalize the canonical name for comparison
    # Remove .pdf extension if present for comparison
    base_name = canonical_name
    if base_name.endswith(".pdf"):
        base_name = base_name[:-4]
    
    # Try both with and without .pdf extension
    name_variations = [
        canonical_name,
        f"{base_name}.pdf" if not canonical_name.endswith(".pdf") else None,
        base_name,
    ]
    name_variations = [name for name in name_variations if name is not None]
    
    s3_client = boto3.client("s3", region_name=region)
    
    # Paginate through all objects in the bucket
    paginator = s3_client.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=bucket_name)
    
    for page in page_iterator:
        if "Contents" not in page:
            continue
            
        for obj in page["Contents"]:
            s3_key = obj["Key"]
            
            # Extract filename from S3 key (format: document_id/filename)
            # Handle cases where there might be subdirectories
            parts = s3_key.split("/")
            if len(parts) < 2:
                continue  # Skip objects not in expected format
            
            filename = parts[-1]
            
            # Check if filename matches any variation of canonical_name
            for name_variant in name_variations:
                if filename == name_variant:
                    # Found a match! Download it
                    try:
                        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
                        file_bytes = response["Body"].read()
                        
                        logger.info(
                            "Found and downloaded PDF from S3 by name: s3://%s/%s (size: %d bytes)",
                            bucket_name,
                            s3_key,
                            len(file_bytes),
                        )
                        return file_bytes
                    except ClientError as exc:
                        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
                        error_message = exc.response.get("Error", {}).get("Message", str(exc))
                        logger.error(
                            "S3 download failed for matched key: %s - %s (bucket: %s, key: %s)",
                            error_code,
                            error_message,
                            bucket_name,
                            s3_key,
                        )
                        raise RuntimeError(
                            f"S3 download failed: {error_code} - {error_message}"
                        ) from exc
    
    # No match found
    raise RuntimeError(
        f"PDF not found in S3 with canonical name '{canonical_name}'"
    )

