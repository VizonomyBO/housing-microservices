"""
Table Normalizer Lambda - Normalizes extracted tables into structured JSON.

This Lambda:
1. Reads the structured JSON from marker-converter
2. Extracts and normalizes table blocks (header/body cells)
3. Generates schema summaries for retrieval
4. Stores normalized tables in S3 under /tables/
5. Creates artifact records via shared_data_layer
6. Updates document stage and ingestion job
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import boto3
from pydantic import BaseModel, Field

# Add common utilities to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.db import get_async_session
from common.events import emit_progress_event
from common.ingestion import (
    IngestionJobManager,
    update_document_stage,
    create_artifact_record,
)

from core.logging import get_logger
from core.exceptions import NormalizationError, S3Error

logger = get_logger(__name__)

# Configuration
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "vizonomy-processed-artifacts")


class NormalizationInput(BaseModel):
    """Input model from Step Functions."""
    
    ingestion_id: str
    document_id: str
    structured_json_key: str
    trace_id: str


class TableCell(BaseModel):
    """Represents a normalized table cell."""
    
    row: int
    col: int
    value: str
    is_header: bool = False
    colspan: int = 1
    rowspan: int = 1


class NormalizedTable(BaseModel):
    """Represents a fully normalized table."""
    
    table_id: str
    document_id: str
    page_number: int
    footnote_ref: str
    caption: Optional[str] = None
    
    # Structure
    headers: list[str]
    column_types: list[str]  # e.g., ["string", "number", "date"]
    rows: list[list[str]]
    
    # Metadata
    row_count: int
    col_count: int
    
    # Schema summary for retrieval
    schema_summary: str


class SchemaSummary(BaseModel):
    """Schema summary for a table (used in retrieval)."""
    
    table_id: str
    footnote_ref: str
    caption: Optional[str]
    columns: list[dict]  # [{name, type, sample_values}]
    summary: str


class NormalizationOutput(BaseModel):
    """Output model for table normalizer."""
    
    ingestion_id: str
    document_id: str
    tables_prefix: str  # S3 prefix for normalized tables
    table_count: int
    schema_summaries: list[dict]
    processing_time_ms: int


def download_from_s3(bucket: str, key: str) -> str:
    """Download a file from S3 and return its content."""
    s3 = boto3.client("s3")
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")
        logger.info(f"Downloaded s3://{bucket}/{key}")
        return content
    except Exception as e:
        logger.error(f"Failed to download from S3: {e}")
        raise S3Error(f"Failed to download file: {e}")


def upload_to_s3(
    bucket: str,
    key: str,
    content: str,
    content_type: str = "application/json",
) -> int:
    """Upload content to S3 and return byte size."""
    s3 = boto3.client("s3")
    content_bytes = content.encode("utf-8")
    
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content_bytes,
            ContentType=content_type,
        )
        logger.info(f"Uploaded to s3://{bucket}/{key}")
        return len(content_bytes)
    except Exception as e:
        logger.error(f"Failed to upload to S3: {e}")
        raise S3Error(f"Failed to upload file: {e}")


def infer_column_type(values: list[str]) -> str:
    """Infer the data type of a column based on its values."""
    if not values:
        return "string"
    
    # Check for numeric values
    numeric_count = 0
    date_count = 0
    
    for val in values:
        if not val or val.strip() == "":
            continue
        
        # Try numeric
        cleaned = re.sub(r"[,$%()]", "", val.strip())
        try:
            float(cleaned)
            numeric_count += 1
            continue
        except ValueError:
            pass
        
        # Try date patterns
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"\d{1,2}\s+\w+\s+\d{4}",
        ]
        for pattern in date_patterns:
            if re.match(pattern, val.strip()):
                date_count += 1
                break
    
    # Determine type based on majority
    total = len([v for v in values if v and v.strip()])
    if total == 0:
        return "string"
    
    if numeric_count / total > 0.5:
        return "number"
    if date_count / total > 0.5:
        return "date"
    
    return "string"


def parse_markdown_table(markdown: str) -> tuple[list[str], list[list[str]]]:
    """
    Parse a markdown table into headers and rows.
    
    Returns:
        (headers, rows) where headers is a list of column names
        and rows is a list of row data (each row is a list of cell values)
    """
    lines = [l.strip() for l in markdown.strip().split("\n") if l.strip()]
    
    if not lines:
        return [], []
    
    headers = []
    rows = []
    
    for i, line in enumerate(lines):
        # Skip separator line (e.g., |---|---|)
        if re.match(r"^\|[\s\-:|]+\|$", line):
            continue
        
        # Parse cells
        cells = [c.strip() for c in line.split("|")]
        # Remove empty first/last cells from split
        cells = [c for c in cells if c or (cells.index(c) not in [0, len(cells)-1])]
        cells = [c.strip() for c in cells]
        
        if i == 0:
            headers = cells
        else:
            rows.append(cells)
    
    return headers, rows


def normalize_table(
    table_data: dict,
    document_id: str,
) -> NormalizedTable:
    """
    Normalize a table block into structured format.
    
    Args:
        table_data: Table data from structured JSON (has markdown, html, caption, etc.)
        document_id: The document ID
    
    Returns:
        NormalizedTable with structured data
    """
    table_id = table_data.get("block_id", f"table_{uuid.uuid4().hex[:8]}")
    page_number = table_data.get("page_number", 0)
    footnote_ref = table_data.get("footnote_ref", f"[Table]")
    caption = table_data.get("caption")
    markdown = table_data.get("markdown", "")
    
    # Parse the markdown table
    headers, rows = parse_markdown_table(markdown)
    
    # Infer column types
    column_types = []
    for col_idx in range(len(headers)):
        col_values = [row[col_idx] if col_idx < len(row) else "" for row in rows]
        col_type = infer_column_type(col_values)
        column_types.append(col_type)
    
    # Generate schema summary
    schema_parts = []
    for i, (header, col_type) in enumerate(zip(headers, column_types)):
        sample_values = [row[i] if i < len(row) else "" for row in rows[:3]]
        sample_str = ", ".join([f'"{v}"' for v in sample_values if v])
        schema_parts.append(f"{header} ({col_type})")
    
    schema_summary = f"{footnote_ref}: {', '.join(schema_parts)}"
    if caption:
        schema_summary = f"{caption}. {schema_summary}"
    
    return NormalizedTable(
        table_id=table_id,
        document_id=document_id,
        page_number=page_number,
        footnote_ref=footnote_ref,
        caption=caption,
        headers=headers,
        column_types=column_types,
        rows=rows,
        row_count=len(rows),
        col_count=len(headers),
        schema_summary=schema_summary,
    )


def generate_schema_summary(table: NormalizedTable) -> SchemaSummary:
    """Generate a schema summary for retrieval indexing."""
    columns = []
    
    for i, (header, col_type) in enumerate(zip(table.headers, table.column_types)):
        # Get sample values
        sample_values = [
            row[i] if i < len(row) else "" 
            for row in table.rows[:5]
        ]
        sample_values = [v for v in sample_values if v][:3]
        
        columns.append({
            "name": header,
            "type": col_type,
            "sample_values": sample_values,
        })
    
    summary = f"{table.footnote_ref}"
    if table.caption:
        summary += f": {table.caption}"
    summary += f". {table.row_count} rows, columns: {', '.join(table.headers)}"
    
    return SchemaSummary(
        table_id=table.table_id,
        footnote_ref=table.footnote_ref,
        caption=table.caption,
        columns=columns,
        summary=summary,
    )


async def handler_async(event: dict, context: Any) -> dict:
    """Async handler implementation."""
    start_time = datetime.now(timezone.utc)
    request_id = getattr(context, "aws_request_id", None) or "local-test"
    
    logger.set_request_id(request_id)
    logger.info("Table normalizer Lambda invoked", extra={"event": event})
    
    try:
        # Parse input
        input_data = NormalizationInput.model_validate(event)
        
        ingestion_id = input_data.ingestion_id
        document_id = input_data.document_id
        trace_id = input_data.trace_id
        
        # Download structured JSON from marker-converter
        structured_json_str = download_from_s3(
            PROCESSED_BUCKET,
            input_data.structured_json_key,
        )
        structured_json = json.loads(structured_json_str)
        
        # Extract tables from structured JSON
        tables_data = structured_json.get("tables", [])
        logger.info(f"Found {len(tables_data)} tables to normalize")
        
        # Normalize each table
        normalized_tables: list[NormalizedTable] = []
        schema_summaries: list[SchemaSummary] = []
        
        for table_data in tables_data:
            try:
                normalized = normalize_table(table_data, document_id)
                normalized_tables.append(normalized)
                
                summary = generate_schema_summary(normalized)
                schema_summaries.append(summary)
                
            except Exception as e:
                logger.warning(f"Failed to normalize table: {e}")
                continue
        
        # Upload normalized tables to S3
        tables_prefix = f"tables/{ingestion_id}"
        
        async with get_async_session() as session:
            for table in normalized_tables:
                table_key = f"{tables_prefix}/{table.table_id}.json"
                table_json = table.model_dump_json(indent=2)
                byte_size = upload_to_s3(PROCESSED_BUCKET, table_key, table_json)
                
                # Create artifact record
                await create_artifact_record(
                    session,
                    document_id=UUID(document_id),
                    artifact_type="normalized_table",
                    s3_key=table_key,
                    s3_bucket=PROCESSED_BUCKET,
                    byte_size=byte_size,
                    metadata={
                        "table_id": table.table_id,
                        "footnote_ref": table.footnote_ref,
                        "row_count": table.row_count,
                        "col_count": table.col_count,
                    },
                )
            
            await session.commit()
        
        # Upload schema summaries index
        summaries_key = f"{tables_prefix}/schema_summaries.json"
        summaries_json = json.dumps(
            [s.model_dump() for s in schema_summaries],
            indent=2,
        )
        upload_to_s3(PROCESSED_BUCKET, summaries_key, summaries_json)
        
        # Calculate processing time
        end_time = datetime.now(timezone.utc)
        processing_time_ms = int((end_time - start_time).total_seconds() * 1000)
        
        output = NormalizationOutput(
            ingestion_id=ingestion_id,
            document_id=document_id,
            tables_prefix=tables_prefix,
            table_count=len(normalized_tables),
            schema_summaries=[s.model_dump() for s in schema_summaries],
            processing_time_ms=processing_time_ms,
        )
        
        logger.info(
            "Table normalization complete",
            extra={
                "table_count": len(normalized_tables),
                "processing_time_ms": processing_time_ms,
            },
        )
        
        return output.model_dump()
        
    except Exception as e:
        logger.error(f"Table normalization failed: {e}", exc_info=True)
        raise NormalizationError(f"Table normalization failed: {e}")


def handler(event: dict, context: Any) -> dict:
    """Lambda handler entry point."""
    import asyncio
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(handler_async(event, context))
    finally:
        loop.close()

