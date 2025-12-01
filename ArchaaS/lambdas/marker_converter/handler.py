"""
Document Converter Lambda - Using markitdown

Converts PDF/DOCX to Markdown using Microsoft's markitdown library.
Lightweight alternative to Marker - no ML models required.
"""
import os
import json
import tempfile
import logging
from typing import Any, Dict, Optional

import boto3
from markitdown import MarkItDown

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
RAW_BUCKET = os.environ.get("RAW_DOCUMENTS_BUCKET", "")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")

# Initialize S3 client
s3 = boto3.client("s3")

# Initialize markitdown converter
md_converter = MarkItDown()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Convert document to Markdown.
    
    Expected input:
    {
        "document_id": "uuid",
        "ingestion_id": "uuid",
        "s3_bucket": "bucket-name",
        "s3_key": "path/to/file.pdf",
        "source_type": "pdf",
        "trace_id": "request-id"
    }
    """
    logger.info(f"Conversion request: {json.dumps(event)}")
    
    document_id = event.get("document_id")
    ingestion_id = event.get("ingestion_id")
    bucket = event.get("s3_bucket") or event.get("bucket")
    key = event.get("s3_key") or event.get("key")
    source_type = event.get("source_type", "pdf")
    trace_id = event.get("trace_id", "")
    
    if not all([document_id, bucket, key]):
        return {
            "statusCode": 400,
            "error": "Missing required fields: document_id, bucket, key"
        }
    
    try:
        # Download file from S3
        with tempfile.NamedTemporaryFile(suffix=f".{source_type}", delete=False) as tmp:
            logger.info(f"Downloading s3://{bucket}/{key}")
            s3.download_file(bucket, key, tmp.name)
            local_path = tmp.name
        
        # Convert to markdown using markitdown
        logger.info(f"Converting {document_id} with markitdown")
        result = md_converter.convert(local_path)
        markdown_content = result.text_content
        
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
                "converter": "markitdown"
            }
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
            "tables_count": markdown_content.count("|") // 10,  # Rough estimate
            "figures_count": markdown_content.count("!["),
        }
        
        metadata_key = f"{output_prefix}/metadata.json"
        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=metadata_key,
            Body=json.dumps(metadata).encode("utf-8"),
            ContentType="application/json"
        )
        
        # Cleanup temp file
        os.unlink(local_path)
        
        logger.info(f"Conversion complete for {document_id}")
        
        return {
            "statusCode": 200,
            "document_id": document_id,
            "ingestion_id": ingestion_id,
            "markdown_key": markdown_key,
            "metadata_key": metadata_key,
            "structured_json_key": metadata_key,
            "figures_prefix": f"{output_prefix}/figures/",
            "tables_count": metadata["tables_count"],
            "figures_count": metadata["figures_count"],
        }
        
    except Exception as e:
        logger.error(f"Conversion failed: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "error": str(e),
            "document_id": document_id
        }
