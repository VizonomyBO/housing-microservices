"""Document Converter Lambda - Using MarkItDown (pdfs -> markdown).

Conversion errors are treated as fatal so the ingestion pipeline marks the
document failed instead of emitting placeholder content.
"""

import json
import logging
import os
import re
import tempfile
from typing import Any

import boto3
from markitdown import FileConversionException, MarkItDown, UnsupportedFormatException

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
RAW_BUCKET = os.environ.get("RAW_DOCUMENTS_BUCKET", "")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")

# Initialize S3 client
s3 = boto3.client("s3")

# Single MarkItDown instance reused across invocations
markitdown = MarkItDown()


class MarkdownConversionError(Exception):
    """Raised when MarkItDown returns empty content."""


def extract_pdf_to_markdown(pdf_path: str) -> tuple[str, int, int]:
    """Extract PDF content to Markdown using MarkItDown."""
    result = markitdown.convert(pdf_path)
    markdown_content = result.text_content or ""

    # Some converters populate metadata; fall back to zeros if missing.
    meta = getattr(result, "metadata", {}) or {}
    pages = _safe_int(meta.get("pages")) if isinstance(meta, dict) else 0
    tables = _safe_int(meta.get("tables")) if isinstance(meta, dict) else 0

    cleaned = clean_text(markdown_content)
    if not cleaned:
        raise MarkdownConversionError("Empty content after MarkItDown conversion")

    return cleaned, tables, pages


def clean_text(text: str) -> str:
    """Normalize whitespace in markdown content."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Convert document to Markdown.

    Expected input:
    {
        "document_id": "uuid",
        "ingestion_id": "uuid",
        "bucket": "bucket-name",
        "key": "path/to/file.pdf",
        "source_type": "pdf",
        "trace_id": "request-id"
    }
    """
    logger.info(f"Conversion request: {json.dumps(event)}")

    document_id = event.get("document_id")
    ingestion_id = event.get("ingestion_id")
    bucket = event.get("bucket") or event.get("s3_bucket")
    key = event.get("key") or event.get("s3_key")
    source_type = event.get("source_type", "pdf")
    trace_id = event.get("trace_id", "")

    if not all([document_id, bucket, key]):
        return {
            "statusCode": 400,
            "error": "Missing required fields: document_id, bucket, key",
        }

    local_path = None
    try:
        # Download file from S3
        with tempfile.NamedTemporaryFile(suffix=f".{source_type}", delete=False) as tmp:
            logger.info(f"Downloading s3://{bucket}/{key}")
            s3.download_file(bucket, key, tmp.name)
            local_path = tmp.name

        # Convert to markdown
        logger.info(f"Converting {document_id} with MarkItDown")
        try:
            markdown_content, tables_count, pages_count = extract_pdf_to_markdown(
                local_path
            )
        except (
            UnsupportedFormatException,
            FileConversionException,
            MarkdownConversionError,
        ) as err:
            logger.error(
                "Conversion failed for %s: %s", document_id, err, exc_info=True
            )
            raise RuntimeError(f"Conversion failed for {document_id}: {err}") from err

        # Upload markdown to S3
        output_prefix = f"processed/{document_id}"
        markdown_key = f"{output_prefix}/content.md"

        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=markdown_key,
            Body=markdown_content.encode("utf-8"),
            ContentType="text/markdown",
            Metadata={
                "document_id": document_id,
                "source_type": source_type,
                "converter": "markitdown",
            },
        )
        logger.info(f"Uploaded markdown to s3://{PROCESSED_BUCKET}/{markdown_key}")

        # Create metadata JSON
        metadata = {
            "document_id": document_id,
            "ingestion_id": ingestion_id,
            "source_type": source_type,
            "converter": "markitdown",
            "markdown_key": markdown_key,
            "content_length": len(markdown_content),
            "pages_count": pages_count,
            "tables_count": tables_count,
            "figures_count": 0,  # pdfplumber doesn't extract images to separate files
        }

        metadata_key = f"{output_prefix}/metadata.json"
        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=metadata_key,
            Body=json.dumps(metadata).encode("utf-8"),
            ContentType="application/json",
        )

        logger.info(
            f"Conversion complete for {document_id}: {pages_count} pages, {tables_count} tables"
        )

        return {
            "statusCode": 200,
            "document_id": document_id,
            "ingestion_id": ingestion_id,
            "markdown_key": markdown_key,
            "metadata_key": metadata_key,
            "structured_json_key": metadata_key,
            "figures_prefix": f"{output_prefix}/figures/",
            "tables_count": tables_count,
            "figures_count": 0,
            "pages_count": pages_count,
        }

    except Exception as e:
        logger.error(f"Conversion failed: {e}", exc_info=True)
        raise RuntimeError(f"Conversion failed for {document_id}: {e}") from e
    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.unlink(local_path)
            except OSError:
                logger.warning("Failed to clean up temp file %s", local_path)
