"""
Chunk Builder Lambda - Splits converted documents into semantic chunks.

This Lambda:
1. Reads converted markdown/JSON from S3
2. Splits content into semantic chunks (~500 tokens)
3. Preserves document structure (headers, sections)
4. Maintains references to tables and figures via footnotes
5. Outputs JSONL files for embedding
6. Creates artifact records via shared_data_layer
"""

import json
import os
import re
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field

import boto3
from pydantic import BaseModel, Field

# Add common utilities to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.db import get_async_session
from common.ingestion import create_artifact_record

from core.logging import get_logger
from core.exceptions import ChunkingError, S3Error, ValidationError

logger = get_logger(__name__)

# Configuration
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "vizonomy-processed-artifacts")
TARGET_CHUNK_TOKENS = int(os.environ.get("TARGET_CHUNK_TOKENS", "500"))
MAX_CHUNK_TOKENS = int(os.environ.get("MAX_CHUNK_TOKENS", "1000"))
MIN_CHUNK_TOKENS = int(os.environ.get("MIN_CHUNK_TOKENS", "50"))
OVERLAP_TOKENS = int(os.environ.get("OVERLAP_TOKENS", "50"))

# Approximate tokens per character (for English)
CHARS_PER_TOKEN = 4


class ChunkingInput(BaseModel):
    """Input model from Step Functions."""
    
    ingestion_id: str
    document_id: str
    markdown_key: str
    structured_json_key: str
    country_code: str = "UNK"
    language: str = "en"
    trace_id: str


class Chunk(BaseModel):
    """A semantic chunk of document content."""
    
    chunk_id: str
    document_id: str
    ingestion_id: str
    sequence: int  # Order within document
    content: str
    token_count: int
    char_count: int
    content_hash: str  # For deduplication
    
    # Structure preservation
    section_path: list[str] = Field(default_factory=list)  # e.g., ["Introduction", "Background"]
    page_numbers: list[int] = Field(default_factory=list)
    
    # References
    table_refs: list[str] = Field(default_factory=list)  # e.g., ["[Table 1]", "[Table 2]"]
    figure_refs: list[str] = Field(default_factory=list)  # e.g., ["[Figure 1]"]
    
    # Metadata
    metadata: dict = Field(default_factory=dict)


class ChunkingOutput(BaseModel):
    """Output model for chunk builder."""
    
    ingestion_id: str
    document_id: str
    chunks_key: str  # S3 key for JSONL file
    chunk_count: int
    total_tokens: int
    total_chars: int
    processing_time_ms: int


@dataclass
class SectionContext:
    """Tracks current section hierarchy."""
    
    headers: list[tuple[int, str]] = field(default_factory=list)  # (level, title)
    current_page: int = 1
    
    def update_header(self, level: int, title: str) -> None:
        """Update section hierarchy when a new header is encountered."""
        # Remove headers at same or lower level
        self.headers = [(l, t) for l, t in self.headers if l < level]
        self.headers.append((level, title))
    
    def get_section_path(self) -> list[str]:
        """Get current section path."""
        return [title for _, title in self.headers]


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


def upload_to_s3(bucket: str, key: str, content: str) -> str:
    """Upload content to S3."""
    s3 = boto3.client("s3")
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="application/x-ndjson",
        )
        logger.info(f"Uploaded to s3://{bucket}/{key}")
        return f"s3://{bucket}/{key}"
    except Exception as e:
        logger.error(f"Failed to upload to S3: {e}")
        raise S3Error(f"Failed to upload file: {e}")


def estimate_tokens(text: str) -> int:
    """Estimate token count from text."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def compute_content_hash(content: str, document_id: str, sequence: int) -> str:
    """Compute a deterministic hash for chunk deduplication."""
    hash_input = f"{document_id}:{sequence}:{content}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:32]


def extract_references(text: str) -> tuple[list[str], list[str]]:
    """Extract table and figure references from text."""
    table_refs = re.findall(r"\[Table \d+\]", text)
    figure_refs = re.findall(r"\[Figure \d+\]", text)
    return list(set(table_refs)), list(set(figure_refs))


def split_into_paragraphs(markdown: str) -> list[tuple[str, Optional[tuple[int, str]]]]:
    """
    Split markdown into paragraphs, preserving headers.
    Returns list of (paragraph_text, optional_header_info).
    header_info is (level, title) if the paragraph starts with a header.
    """
    paragraphs = []
    
    # Split by double newlines (paragraph separator)
    blocks = re.split(r"\n\n+", markdown)
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        # Check if this is a header
        header_match = re.match(r"^(#{1,6})\s+(.+)$", block, re.MULTILINE)
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            paragraphs.append((block, (level, title)))
        else:
            paragraphs.append((block, None))
    
    return paragraphs


def recursive_character_split(
    paragraphs: list[tuple[str, Optional[tuple[int, str]]]],
    document_id: str,
    ingestion_id: str,
    target_tokens: int = TARGET_CHUNK_TOKENS,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """
    Split paragraphs into chunks using recursive character splitting.
    Preserves structure by tracking headers.
    """
    chunks = []
    context = SectionContext()
    
    current_content: list[str] = []
    current_tokens = 0
    sequence = 0
    
    def flush_chunk() -> None:
        """Flush current content as a chunk."""
        nonlocal current_content, current_tokens, sequence
        
        if not current_content:
            return
        
        content = "\n\n".join(current_content)
        if estimate_tokens(content) < MIN_CHUNK_TOKENS:
            # Too small, keep accumulating
            return
        
        table_refs, figure_refs = extract_references(content)
        
        chunk = Chunk(
            chunk_id=f"ch_{uuid.uuid4().hex[:12]}",
            document_id=document_id,
            ingestion_id=ingestion_id,
            sequence=sequence,
            content=content,
            token_count=estimate_tokens(content),
            char_count=len(content),
            content_hash=compute_content_hash(content, document_id, sequence),
            section_path=context.get_section_path(),
            page_numbers=[context.current_page],
            table_refs=table_refs,
            figure_refs=figure_refs,
            metadata={},
        )
        chunks.append(chunk)
        sequence += 1
        
        # Keep overlap for context continuity
        if overlap_tokens > 0 and len(current_content) > 1:
            # Keep last paragraph for overlap
            overlap_text = current_content[-1]
            current_content = [overlap_text] if estimate_tokens(overlap_text) <= overlap_tokens else []
            current_tokens = estimate_tokens(overlap_text) if current_content else 0
        else:
            current_content = []
            current_tokens = 0
    
    for para_text, header_info in paragraphs:
        # Update section context if this is a header
        if header_info:
            level, title = header_info
            context.update_header(level, title)
        
        # Check for page markers
        page_match = re.search(r"## Page (\d+)", para_text)
        if page_match:
            context.current_page = int(page_match.group(1))
        
        para_tokens = estimate_tokens(para_text)
        
        # If single paragraph exceeds max, split it further
        if para_tokens > max_tokens:
            # Flush current chunk first
            flush_chunk()
            
            # Split long paragraph by sentences
            sentences = re.split(r"(?<=[.!?])\s+", para_text)
            
            for sentence in sentences:
                sent_tokens = estimate_tokens(sentence)
                
                if current_tokens + sent_tokens > target_tokens:
                    flush_chunk()
                
                current_content.append(sentence)
                current_tokens += sent_tokens
        else:
            # Check if adding this paragraph would exceed target
            if current_tokens + para_tokens > target_tokens:
                flush_chunk()
            
            current_content.append(para_text)
            current_tokens += para_tokens
    
    # Flush remaining content
    if current_content:
        flush_chunk()
    
    return chunks


def process_structured_data(
    structured_json: dict,
    document_id: str,
    ingestion_id: str,
) -> list[Chunk]:
    """
    Process structured JSON data for additional context.
    Creates special chunks for tables and figures with their footnotes.
    """
    special_chunks = []
    sequence_start = 10000  # High number to not conflict with text chunks
    
    # Process tables
    tables = structured_json.get("tables", [])
    for i, table in enumerate(tables):
        footnote_ref = table.get("footnote_ref", f"[Table {i+1}]")
        content = f"# {footnote_ref}\n\n"
        
        if table.get("caption"):
            content += f"**Caption:** {table['caption']}\n\n"
        
        content += f"**Location:** Page {table.get('page_number', 'Unknown')}\n\n"
        content += table.get("markdown", table.get("html", ""))
        
        chunk = Chunk(
            chunk_id=f"ch_table_{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            ingestion_id=ingestion_id,
            sequence=sequence_start + i,
            content=content,
            token_count=estimate_tokens(content),
            char_count=len(content),
            content_hash=compute_content_hash(content, document_id, sequence_start + i),
            section_path=["Appendix", "Tables"],
            page_numbers=[table.get("page_number", 0)],
            table_refs=[footnote_ref],
            figure_refs=[],
            metadata={"type": "table", "footnote_ref": footnote_ref},
        )
        special_chunks.append(chunk)
    
    # Process figures
    figures = structured_json.get("figures", [])
    for i, figure in enumerate(figures):
        footnote_ref = figure.get("footnote_ref", f"[Figure {i+1}]")
        content = f"# {footnote_ref}\n\n"
        
        if figure.get("caption"):
            content += f"**Caption:** {figure['caption']}\n\n"
        
        content += f"**Location:** Page {figure.get('page_number', 'Unknown')}\n\n"
        content += f"**Image:** {figure.get('image_key', 'N/A')}\n"
        
        chunk = Chunk(
            chunk_id=f"ch_fig_{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            ingestion_id=ingestion_id,
            sequence=sequence_start + 1000 + i,
            content=content,
            token_count=estimate_tokens(content),
            char_count=len(content),
            content_hash=compute_content_hash(content, document_id, sequence_start + 1000 + i),
            section_path=["Appendix", "Figures"],
            page_numbers=[figure.get("page_number", 0)],
            table_refs=[],
            figure_refs=[footnote_ref],
            metadata={"type": "figure", "footnote_ref": footnote_ref, "image_key": figure.get("image_key")},
        )
        special_chunks.append(chunk)
    
    return special_chunks


async def handler_async(event: dict, context: Any) -> dict:
    """
    Async Lambda handler for chunk building.
    
    Expected input (from Step Functions - output of marker-converter):
    {
        "ingestion_id": "ing-xxx",
        "document_id": "doc-xxx",
        "markdown_key": "converted/ing-xxx/document.md",
        "structured_json_key": "converted/ing-xxx/structured.json",
        "country_code": "ARG",
        "language": "en",
        "trace_id": "trace-xxx"
    }
    """
    from uuid import UUID as PyUUID
    import asyncio
    
    start_time = datetime.now(timezone.utc)
    request_id = getattr(context, "aws_request_id", None) or str(uuid.uuid4())
    
    logger.set_request_id(request_id)
    logger.info("Chunk builder Lambda invoked", extra={"event": event})
    
    try:
        # Parse input
        input_data = ChunkingInput.model_validate(event)
        
        ingestion_id = input_data.ingestion_id
        document_id = input_data.document_id
        
        # Download converted files
        markdown_content = download_from_s3(PROCESSED_BUCKET, input_data.markdown_key)
        structured_json_str = download_from_s3(PROCESSED_BUCKET, input_data.structured_json_key)
        structured_json = json.loads(structured_json_str)
        
        # Split markdown into paragraphs
        paragraphs = split_into_paragraphs(markdown_content)
        logger.info(f"Split into {len(paragraphs)} paragraphs")
        
        # Create text chunks
        text_chunks = recursive_character_split(
            paragraphs,
            document_id,
            ingestion_id,
        )
        logger.info(f"Created {len(text_chunks)} text chunks")
        
        # Create special chunks for tables and figures
        special_chunks = process_structured_data(
            structured_json,
            document_id,
            ingestion_id,
        )
        logger.info(f"Created {len(special_chunks)} special chunks (tables/figures)")
        
        # Combine all chunks
        all_chunks = text_chunks + special_chunks
        
        # Create JSONL output
        jsonl_lines = [json.dumps(chunk.model_dump()) for chunk in all_chunks]
        jsonl_content = "\n".join(jsonl_lines)
        
        # Upload JSONL
        output_prefix = f"chunks/{ingestion_id}"
        chunks_key = f"{output_prefix}/chunks.jsonl"
        upload_to_s3(PROCESSED_BUCKET, chunks_key, jsonl_content)
        
        # Calculate totals
        total_tokens = sum(c.token_count for c in all_chunks)
        total_chars = sum(c.char_count for c in all_chunks)
        
        # Create artifact record via shared_data_layer
        async with get_async_session() as session:
            await create_artifact_record(
                session,
                document_id=PyUUID(document_id),
                artifact_type="chunk_manifest",
                s3_key=chunks_key,
                s3_bucket=PROCESSED_BUCKET,
                byte_size=len(jsonl_content.encode("utf-8")),
                metadata={
                    "chunk_count": len(all_chunks),
                    "total_tokens": total_tokens,
                    "text_chunks": len(text_chunks),
                    "special_chunks": len(special_chunks),
                },
            )
            await session.commit()
        
        # Calculate processing time
        end_time = datetime.now(timezone.utc)
        processing_time_ms = int((end_time - start_time).total_seconds() * 1000)
        
        output = ChunkingOutput(
            ingestion_id=ingestion_id,
            document_id=document_id,
            chunks_key=chunks_key,
            chunk_count=len(all_chunks),
            total_tokens=total_tokens,
            total_chars=total_chars,
            processing_time_ms=processing_time_ms,
        )
        
        logger.info(
            "Chunking complete",
            extra={
                "chunk_count": len(all_chunks),
                "total_tokens": total_tokens,
                "processing_time_ms": processing_time_ms,
            },
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise
    except ChunkingError as e:
        logger.error(f"Chunking error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise ChunkingError(f"Chunk building failed: {e}")


def handler(event: dict, context: Any) -> dict:
    """Lambda handler entry point."""
    import asyncio
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(handler_async(event, context))
    finally:
        loop.close()

