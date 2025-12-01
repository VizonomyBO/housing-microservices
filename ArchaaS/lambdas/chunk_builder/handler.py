"""
Chunk Builder Lambda - Splits converted documents into semantic chunks.

Reads markdown from S3, splits into chunks, outputs JSONL for embedding.
"""

import json
import os
import re
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional, List
from dataclasses import dataclass, field

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "vizonomy-processed-artifacts")
TARGET_CHUNK_TOKENS = int(os.environ.get("TARGET_CHUNK_TOKENS", "500"))
MAX_CHUNK_TOKENS = int(os.environ.get("MAX_CHUNK_TOKENS", "1000"))
MIN_CHUNK_TOKENS = int(os.environ.get("MIN_CHUNK_TOKENS", "50"))
OVERLAP_TOKENS = int(os.environ.get("OVERLAP_TOKENS", "50"))

# Approximate tokens per character (for English)
CHARS_PER_TOKEN = 4

# S3 client
s3 = boto3.client("s3")


@dataclass
class Chunk:
    """A chunk of text with metadata."""
    id: str
    content: str
    document_id: str
    chunk_index: int
    page_numbers: List[int] = field(default_factory=list)
    section_title: Optional[str] = None
    token_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "page_numbers": self.page_numbers,
            "section_title": self.section_title,
            "token_count": self.token_count,
        }


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return len(text) // CHARS_PER_TOKEN


def split_into_chunks(
    content: str,
    document_id: str,
    target_tokens: int = TARGET_CHUNK_TOKENS,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> List[Chunk]:
    """Split content into semantic chunks."""
    chunks = []
    
    # Split by page markers and headers
    sections = re.split(r'\n(##?\s+Page\s+\d+|\n#{1,3}\s+[^\n]+)', content)
    
    current_text = ""
    current_page = 1
    current_section = None
    chunk_index = 0
    
    for section in sections:
        if not section.strip():
            continue
            
        # Check for page marker
        page_match = re.match(r'##?\s+Page\s+(\d+)', section)
        if page_match:
            current_page = int(page_match.group(1))
            continue
            
        # Check for section header
        header_match = re.match(r'#{1,3}\s+(.+)', section)
        if header_match:
            current_section = header_match.group(1).strip()
            section = section + "\n"
        
        # Add to current chunk
        current_text += section
        
        # Check if we should split
        if estimate_tokens(current_text) >= target_tokens:
            chunk_id = f"{document_id}_{chunk_index:04d}"
            chunk = Chunk(
                id=chunk_id,
                content=current_text.strip(),
                document_id=document_id,
                chunk_index=chunk_index,
                page_numbers=[current_page],
                section_title=current_section,
                token_count=estimate_tokens(current_text),
            )
            chunks.append(chunk)
            
            # Keep overlap
            overlap_chars = overlap_tokens * CHARS_PER_TOKEN
            current_text = current_text[-overlap_chars:] if len(current_text) > overlap_chars else ""
            chunk_index += 1
    
    # Add remaining text
    if current_text.strip() and estimate_tokens(current_text) >= MIN_CHUNK_TOKENS:
        chunk_id = f"{document_id}_{chunk_index:04d}"
        chunk = Chunk(
            id=chunk_id,
            content=current_text.strip(),
            document_id=document_id,
            chunk_index=chunk_index,
            page_numbers=[current_page],
            section_title=current_section,
            token_count=estimate_tokens(current_text),
        )
        chunks.append(chunk)
    
    return chunks


def handler(event: dict, context: Any) -> dict:
    """
    Process converted document and create chunks.
    
    Input:
    {
        "document_id": "uuid",
        "ingestion_id": "uuid",
        "convert_result": {
            "markdown_key": "processed/uuid/content.md",
            ...
        }
    }
    """
    logger.info(f"Chunk builder started: {json.dumps(event)}")
    
    document_id = event.get("document_id")
    ingestion_id = event.get("ingestion_id")
    # markdown_key can be passed directly or nested in convert_result
    markdown_key = event.get("markdown_key") or event.get("convert_result", {}).get("markdown_key")
    
    if not all([document_id, markdown_key]):
        return {
            "statusCode": 400,
            "error": "Missing document_id or markdown_key"
        }
    
    try:
        # Read markdown from S3
        logger.info(f"Reading markdown from s3://{PROCESSED_BUCKET}/{markdown_key}")
        response = s3.get_object(Bucket=PROCESSED_BUCKET, Key=markdown_key)
        content = response["Body"].read().decode("utf-8")
        
        # Split into chunks
        chunks = split_into_chunks(content, document_id)
        logger.info(f"Created {len(chunks)} chunks from document {document_id}")
        
        # Write chunks as JSONL
        output_key = f"processed/{document_id}/chunks.jsonl"
        jsonl_content = "\n".join(json.dumps(c.to_dict()) for c in chunks)
        
        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=output_key,
            Body=jsonl_content.encode("utf-8"),
            ContentType="application/x-ndjson",
            Metadata={
                "document_id": document_id,
                "chunk_count": str(len(chunks)),
            }
        )
        logger.info(f"Uploaded chunks to s3://{PROCESSED_BUCKET}/{output_key}")
        
        return {
            "statusCode": 200,
            "document_id": document_id,
            "ingestion_id": ingestion_id,
            "chunks_key": output_key,
            "chunk_count": len(chunks),
            "total_tokens": sum(c.token_count for c in chunks),
        }
        
    except Exception as e:
        logger.error(f"Chunking failed: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "error": str(e),
            "document_id": document_id,
        }
