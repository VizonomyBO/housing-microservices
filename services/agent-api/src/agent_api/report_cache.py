"""S3 cache client for housing PDF reports."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from agent_api.settings import Settings

logger = logging.getLogger(__name__)

# Reports expire 30 days after generation
REPORT_TTL_DAYS = 30


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
        S3 key in format: reports/report_{country_code}.pdf
    """
    return f"reports/report_{country_code}.pdf"


def _is_report_expired(last_modified: datetime, ttl_days: int = REPORT_TTL_DAYS) -> bool:
    """
    Check if a report is expired based on its last modified date.

    Args:
        last_modified: The LastModified timestamp from S3
        ttl_days: Number of days before a report expires (default: 30)

    Returns:
        True if the report is older than ttl_days, False otherwise
    """
    now = datetime.now(timezone.utc)
    age_days = (now - last_modified).days
    return age_days >= ttl_days


def get_cached_report(
    country_code: str, settings: Settings, skip_expiry_check: bool = False
) -> bytes | None:
    """
    Retrieve cached report from S3 if it exists and is not expired.

    Reports expire 30 days after generation. The pre-generation job on the 25th
    uses skip_cache=True to force regeneration, ensuring reports are refreshed
    before they expire.

    Args:
        country_code: ISO-3 country code (e.g., "USA")
        settings: Application settings
        skip_expiry_check: If True, return the report regardless of age

    Returns:
        PDF bytes if cached report exists and is not expired, None otherwise
    """
    if not settings.s3_housing_pdf_bucket:
        return None

    bucket_name = settings.s3_housing_pdf_bucket
    s3_key = _get_cache_key(country_code)

    try:
        s3_client = _get_s3_client(settings)
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        
        # Check if report is expired (unless skip_expiry_check is True)
        last_modified = response.get("LastModified")
        if last_modified and not skip_expiry_check:
            if _is_report_expired(last_modified):
                age_days = (datetime.now(timezone.utc) - last_modified).days
                logger.info(
                    "Cached report expired (age: %d days, TTL: %d days): s3://%s/%s",
                    age_days,
                    REPORT_TTL_DAYS,
                    bucket_name,
                    s3_key,
                )
                return None
        
        pdf_bytes = response["Body"].read()

        age_info = ""
        if last_modified:
            age_days = (datetime.now(timezone.utc) - last_modified).days
            age_info = f", age: {age_days} days"

        logger.info(
            "Retrieved cached report from S3: s3://%s/%s (size: %d bytes%s)",
            bucket_name,
            s3_key,
            len(pdf_bytes),
            age_info,
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
    country_code: str, pdf_bytes: bytes, settings: Settings
) -> None:
    """
    Upload generated report to S3 cache.

    The report will be stored without a month suffix - it's just the latest
    version for that country. Expiration is based on the S3 object's LastModified
    timestamp (30 days).

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
            Metadata={
                "generated-at": datetime.now(timezone.utc).isoformat(),
                "country-code": country_code,
            },
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
