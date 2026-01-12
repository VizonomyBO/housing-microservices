"""S3 cache client for housing PDF reports."""

from __future__ import annotations

import logging
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from agent_api.settings import Settings

logger = logging.getLogger(__name__)


def _get_s3_client(settings: Settings) -> boto3.client:
    """Initialize and return S3 client with settings."""
    client_kwargs = {"region_name": settings.aws_region}

    if settings.s3_endpoint_url:
        client_kwargs["endpoint_url"] = settings.s3_endpoint_url

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    return boto3.client("s3", **client_kwargs)


def _get_cache_key(country_code: str) -> str:
    """
    Generate S3 cache key for a report.

    Args:
        country_code: ISO-3 country code (e.g., "USA")

    Returns:
        S3 key in format: reports/report_{country_code}_{YYYY-MM}.pdf
    """
    current_month = datetime.now().strftime("%Y-%m")
    return f"reports/report_{country_code}_{current_month}.pdf"


def get_cached_report(country_code: str, settings: Settings) -> bytes | None:
    """
    Retrieve cached report from S3 if it exists.

    Args:
        country_code: ISO-3 country code (e.g., "USA")
        settings: Application settings

    Returns:
        PDF bytes if cached report exists, None otherwise
    """
    if not settings.s3_housing_pdf_bucket:
        return None

    bucket_name = settings.s3_housing_pdf_bucket
    s3_key = _get_cache_key(country_code)

    try:
        s3_client = _get_s3_client(settings)
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        pdf_bytes = response["Body"].read()

        logger.info(
            "Retrieved cached report from S3: s3://%s/%s (size: %d bytes)",
            bucket_name,
            s3_key,
            len(pdf_bytes),
        )
        return pdf_bytes

    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "NoSuchKey":
            logger.debug("No cached report found: s3://%s/%s", bucket_name, s3_key)
        else:
            logger.warning(
                "Failed to retrieve cached report from S3: %s - %s (bucket: %s, key: %s)",
                error_code,
                exc.response.get("Error", {}).get("Message", str(exc)),
                bucket_name,
                s3_key,
            )
        return None
    except Exception as exc:
        logger.warning(
            "Unexpected error retrieving cached report from S3: %s (bucket: %s, key: %s)",
            exc,
            bucket_name,
            s3_key,
        )
        return None


def upload_cached_report(country_code: str, pdf_bytes: bytes, settings: Settings) -> None:
    """
    Upload generated report to S3 cache.

    Args:
        country_code: ISO-3 country code (e.g., "USA")
        pdf_bytes: PDF file content as bytes
        settings: Application settings
    """
    if not settings.s3_housing_pdf_bucket:
        return

    bucket_name = settings.s3_housing_pdf_bucket
    s3_key = _get_cache_key(country_code)

    try:
        s3_client = _get_s3_client(settings)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
            ServerSideEncryption="AES256",
        )

        logger.info(
            "Uploaded report to S3 cache: s3://%s/%s (size: %d bytes)",
            bucket_name,
            s3_key,
            len(pdf_bytes),
        )

    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        logger.warning(
            "Failed to upload report to S3 cache: %s - %s (bucket: %s, key: %s)",
            error_code,
            error_message,
            bucket_name,
            s3_key,
        )
    except Exception as exc:
        logger.warning(
            "Unexpected error uploading report to S3 cache: %s (bucket: %s, key: %s)",
            exc,
            bucket_name,
            s3_key,
        )
