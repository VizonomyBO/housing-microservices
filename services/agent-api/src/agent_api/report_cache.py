"""S3 cache client for housing PDF reports."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

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


def get_next_month() -> str:
    """Get the next month in YYYY-MM format."""
    next_month = datetime.now() + relativedelta(months=1)
    return next_month.strftime("%Y-%m")


def validate_target_month(target_month: str | None) -> str | None:
    """
    Validate target_month format (YYYY-MM).
    
    Returns the validated month string or None if invalid/not provided.
    """
    if not target_month:
        return None
    if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", target_month):
        return target_month
    return None


def _get_cache_key(country_code: str, target_month: str | None = None) -> str:
    """
    Generate S3 cache key for a report.

    Args:
        country_code: ISO-3 country code (e.g., "USA")
        target_month: Optional target month in YYYY-MM format. 
                      If not provided, uses current month.

    Returns:
        S3 key in format: reports/report_{country_code}_{YYYY-MM}.pdf
    """
    month = target_month if target_month else datetime.now().strftime("%Y-%m")
    return f"reports/report_{country_code}_{month}.pdf"


def get_cached_report(
    country_code: str, settings: Settings, target_month: str | None = None
) -> bytes | None:
    """
    Retrieve cached report from S3 if it exists.

    Args:
        country_code: ISO-3 country code (e.g., "USA")
        settings: Application settings
        target_month: Optional target month in YYYY-MM format

    Returns:
        PDF bytes if cached report exists, None otherwise
    """
    if not settings.s3_housing_pdf_bucket:
        return None

    bucket_name = settings.s3_housing_pdf_bucket
    s3_key = _get_cache_key(country_code, target_month)

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


def upload_cached_report(
    country_code: str, pdf_bytes: bytes, settings: Settings, target_month: str | None = None
) -> None:
    """
    Upload generated report to S3 cache.

    Args:
        country_code: ISO-3 country code (e.g., "USA")
        pdf_bytes: PDF file content as bytes
        settings: Application settings
        target_month: Optional target month in YYYY-MM format
    """
    if not settings.s3_housing_pdf_bucket:
        return

    bucket_name = settings.s3_housing_pdf_bucket
    s3_key = _get_cache_key(country_code, target_month)

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

