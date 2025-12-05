"""
Document Converter Lambda - Using pdfplumber

Converts PDF to Markdown using pdfplumber (lightweight).
Extracts text and tables without ML dependencies.
"""

import json
import logging
import os
import re
import tempfile
from typing import Any

import boto3
import pdfplumber
import pypdf
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException
from pypdf.errors import PdfReadError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
RAW_BUCKET = os.environ.get("RAW_DOCUMENTS_BUCKET", "")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")

# Initialize S3 client
s3 = boto3.client("s3")


def extract_pdf_to_markdown(pdf_path: str) -> tuple[str, int, int]:
    """
    Extract PDF content to Markdown format.
    Returns (markdown_content, tables_count, pages_count)
    """
    primary_error: Exception | None = None

    try:
        return _extract_with_pdfplumber(pdf_path)
    except (PdfminerException, PDFSyntaxError) as err:
        primary_error = err
        logger.warning(
            "pdfplumber failed (%s); falling back to pypdf", err, exc_info=False
        )
    except Exception as err:  # pragma: nocover - defensive guard rail
        primary_error = err
        logger.warning("pdfplumber crashed (%s); trying pypdf fallback", err, exc_info=True)

    try:
        return _extract_with_pypdf(pdf_path)
    except PdfReadError as err:
        if primary_error is None:
            primary_error = err
        logger.warning("pypdf fallback failed (%s); generating placeholder", err, exc_info=False)
    except Exception as err:  # pragma: nocover - defensive guard rail
        if primary_error is None:
            primary_error = err
        logger.warning("pypdf crashed (%s); generating placeholder", err, exc_info=True)

    return _build_placeholder_markdown(primary_error)


def _extract_with_pdfplumber(pdf_path: str) -> tuple[str, int, int]:
    """Primary extractor leveraging pdfplumber for tables + text."""
    markdown_parts: list[str] = []
    tables_count = 0

    with pdfplumber.open(pdf_path) as pdf:
        pages_count = len(pdf.pages)

        for i, page in enumerate(pdf.pages):
            markdown_parts.append(f"\n## Page {i + 1}\n")

            tables = page.extract_tables()
            if tables:
                for table in tables:
                    tables_count += 1
                    markdown_parts.append(table_to_markdown(table))
                    markdown_parts.append("\n")

            text = page.extract_text()
            if text:
                markdown_parts.append(clean_text(text))
                markdown_parts.append("\n")

    return "\n".join(markdown_parts), tables_count, pages_count


def _extract_with_pypdf(pdf_path: str) -> tuple[str, int, int]:
    """Fallback extractor using pypdf when pdfplumber cannot parse the file."""
    markdown_parts: list[str] = []
    reader = pypdf.PdfReader(pdf_path, strict=False)
    pages_count = len(reader.pages)

    for i, page in enumerate(reader.pages):
        markdown_parts.append(f"\n## Page {i + 1}\n")
        text = page.extract_text() or ""
        cleaned = clean_text(text)
        if cleaned:
            markdown_parts.append(cleaned)
            markdown_parts.append("\n")

    return "\n".join(markdown_parts), 0, pages_count


def table_to_markdown(table: list) -> str:
    """Convert a table to Markdown format."""
    if not table or not table[0]:
        return ""

    lines = []
    # Header
    header = [str(cell or "").strip() for cell in table[0]]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    # Rows
    for row in table[1:]:
        cells = [str(cell or "").strip().replace("|", "\\|") for cell in row]
        # Pad if row has fewer cells
        while len(cells) < len(header):
            cells.append("")
        lines.append("| " + " | ".join(cells[: len(header)]) + " |")

    return "\n".join(lines)


def clean_text(text: str) -> str:
    """Clean extracted text."""
    # Remove excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _build_placeholder_markdown(error: Exception | None) -> tuple[str, int, int]:
    """Return a minimal markdown payload when both converters fail."""
    logger.error(
        "Conversion failed after all fallbacks; emitting placeholder content (%s)",
        error,
        exc_info=False,
    )
    message_lines = [
        "# Document Conversion Error",
        "",
        "The ingestion pipeline could not parse this PDF with pdfplumber or pypdf.",
        "A placeholder artifact was generated so downstream steps can complete.",
        "",
        "Please re-upload the original document if you need actual content.",
    ]
    if error:
        message_lines.extend(
            [
                "",
                f"> Conversion error: {error}",
            ]
        )
    return "\n".join(message_lines), 0, 0


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
        return {"statusCode": 400, "error": "Missing required fields: document_id, bucket, key"}

    local_path = None
    try:
        # Download file from S3
        with tempfile.NamedTemporaryFile(suffix=f".{source_type}", delete=False) as tmp:
            logger.info(f"Downloading s3://{bucket}/{key}")
            s3.download_file(bucket, key, tmp.name)
            local_path = tmp.name

        # Convert to markdown
        logger.info(f"Converting {document_id} with pdfplumber")
        markdown_content, tables_count, pages_count = extract_pdf_to_markdown(local_path)

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
                "converter": "pdfplumber",
            },
        )
        logger.info(f"Uploaded markdown to s3://{PROCESSED_BUCKET}/{markdown_key}")

        # Create metadata JSON
        metadata = {
            "document_id": document_id,
            "ingestion_id": ingestion_id,
            "source_type": source_type,
            "converter": "pdfplumber",
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
