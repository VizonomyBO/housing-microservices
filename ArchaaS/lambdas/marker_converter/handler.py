"""
Marker Converter Lambda - Converts PDF/DOCX to Markdown with structured output.

This Lambda:
1. Downloads the document from S3
2. Uses Marker library to convert to Markdown/JSON
3. Extracts tables and figures with AI-generated footnotes (OpenAI)
4. Uploads artifacts to S3
5. Returns block inventory for downstream processing
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
import hashlib
import base64
import re

import boto3
from pydantic import BaseModel, Field
from openai import OpenAI

# Marker imports
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser

from core.logging import get_logger
from core.exceptions import (
    ConversionError,
    S3Error,
    ValidationError,
)

logger = get_logger(__name__)

# OpenAI client for footnote generation
_openai_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ConversionError("OPENAI_API_KEY environment variable not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

# Configuration
RAW_BUCKET = os.environ.get("RAW_DOCUMENTS_BUCKET", "vizonomy-raw-documents")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "vizonomy-processed-artifacts")


class ConversionInput(BaseModel):
    """Input model for marker conversion."""
    
    ingestion_id: str
    document_id: str
    s3_key: str
    s3_bucket: str
    converted_key_prefix: Optional[str] = None
    source_type: str = "pdf"
    trace_id: str


class TableBlock(BaseModel):
    """Represents an extracted table."""
    
    block_id: str
    page_number: int
    html: str
    markdown: str
    caption: Optional[str] = None
    footnote_ref: str  # e.g., "[Table 1]"
    position: dict  # polygon coordinates


class FigureBlock(BaseModel):
    """Represents an extracted figure/image."""
    
    block_id: str
    page_number: int
    image_key: str  # S3 key for the image
    caption: Optional[str] = None
    footnote_ref: str  # e.g., "[Figure 1]"
    position: dict
    content_type: str = "image/png"


class PageBlock(BaseModel):
    """Represents a page with its content."""
    
    page_id: int
    markdown_content: str
    tables: list[str] = Field(default_factory=list)  # List of table block_ids
    figures: list[str] = Field(default_factory=list)  # List of figure block_ids
    word_count: int = 0


class ConversionOutput(BaseModel):
    """Output model for marker conversion."""
    
    ingestion_id: str
    document_id: str
    markdown_key: str  # S3 key for converted markdown
    structured_json_key: str  # S3 key for structured JSON
    pages: list[PageBlock]
    tables: list[TableBlock]
    figures: list[FigureBlock]
    total_pages: int
    total_tables: int
    total_figures: int
    metadata: dict
    processing_time_ms: int


# Global converter instance (reuse across invocations for warm starts)
_converter: Optional[PdfConverter] = None


def get_converter() -> PdfConverter:
    """Get or create the Marker PDF converter."""
    global _converter
    
    if _converter is None:
        logger.info("Initializing Marker converter...")
        
        config = {
            "output_format": "json",
            "extract_images": True,
        }
        config_parser = ConfigParser(config)
        
        _converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=create_model_dict(),
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
        )
        logger.info("Marker converter initialized")
    
    return _converter


def download_from_s3(bucket: str, key: str, local_path: str) -> None:
    """Download a file from S3."""
    s3 = boto3.client("s3")
    try:
        s3.download_file(bucket, key, local_path)
        logger.info(f"Downloaded s3://{bucket}/{key} to {local_path}")
    except Exception as e:
        logger.error(f"Failed to download from S3: {e}")
        raise S3Error(f"Failed to download file: {e}")


def upload_to_s3(
    bucket: str,
    key: str,
    content: bytes | str,
    content_type: str = "application/json"
) -> str:
    """Upload content to S3."""
    s3 = boto3.client("s3")
    
    if isinstance(content, str):
        content = content.encode("utf-8")
    
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        logger.info(f"Uploaded to s3://{bucket}/{key}")
        return f"s3://{bucket}/{key}"
    except Exception as e:
        logger.error(f"Failed to upload to S3: {e}")
        raise S3Error(f"Failed to upload file: {e}")


def extract_blocks_with_footnotes(
    rendered: Any,
    ingestion_id: str,
    document_id: str,
) -> tuple[list[PageBlock], list[TableBlock], list[FigureBlock], dict[str, bytes]]:
    """
    Extract pages, tables, and figures from Marker output.
    Adds footnote references for tables and figures.
    """
    pages: list[PageBlock] = []
    tables: list[TableBlock] = []
    figures: list[FigureBlock] = []
    images_to_upload: dict[str, bytes] = {}
    
    table_counter = 1
    figure_counter = 1
    
    def process_block(block: Any, page_id: int, current_markdown: list[str]) -> None:
        """Recursively process blocks."""
        nonlocal table_counter, figure_counter
        
        block_type = getattr(block, "block_type", None)
        block_id = getattr(block, "id", f"block_{uuid.uuid4().hex[:8]}")
        html = getattr(block, "html", "")
        polygon = getattr(block, "polygon", [[0, 0], [0, 0], [0, 0], [0, 0]])
        
        if block_type == "Table":
            footnote_ref = f"[Table {table_counter}]"
            
            # Convert table HTML to markdown (simplified)
            table_md = html_table_to_markdown(html)
            
            # Generate AI-powered footnote for the table
            ai_caption = generate_table_footnote(table_md, table_counter, page_id)
            existing_caption = extract_caption_from_context(html)
            final_caption = existing_caption or ai_caption
            
            table_block = TableBlock(
                block_id=block_id,
                page_number=page_id,
                html=html,
                markdown=table_md,
                caption=final_caption,
                footnote_ref=footnote_ref,
                position={"polygon": polygon},
            )
            tables.append(table_block)
            
            # Add footnote reference and AI-generated caption to markdown
            current_markdown.append(f"\n{table_md}\n\n*{footnote_ref}: {ai_caption}*\n")
            table_counter += 1
            
        elif block_type in ("Figure", "Picture", "Image"):
            footnote_ref = f"[Figure {figure_counter}]"
            
            # Get image data if available
            images = getattr(block, "images", {}) or {}
            image_data = None
            
            for img_id, img_base64 in images.items():
                if isinstance(img_base64, str):
                    try:
                        image_data = base64.b64decode(img_base64)
                    except:
                        pass
                    break
            
            image_key = f"figures/{ingestion_id}/{block_id}.png"
            
            if image_data:
                images_to_upload[image_key] = image_data
            
            # Generate AI-powered footnote for the figure (with vision if image available)
            context_text = "\n".join(current_markdown[-3:]) if current_markdown else ""
            ai_caption = generate_figure_footnote(image_data, figure_counter, page_id, context_text)
            existing_caption = extract_caption_from_context(html)
            final_caption = existing_caption or ai_caption
            
            figure_block = FigureBlock(
                block_id=block_id,
                page_number=page_id,
                image_key=image_key,
                caption=final_caption,
                footnote_ref=footnote_ref,
                position={"polygon": polygon},
            )
            figures.append(figure_block)
            
            # Add footnote reference and AI-generated caption to markdown
            current_markdown.append(f"\n![{footnote_ref}]({image_key})\n\n*{footnote_ref}: {ai_caption}*\n")
            figure_counter += 1
            
        elif block_type in ("Text", "Span", "Paragraph"):
            # Regular text content
            text = html_to_text(html)
            if text.strip():
                current_markdown.append(text)
                
        elif block_type == "SectionHeader":
            # Headers
            level = determine_header_level(html)
            text = html_to_text(html)
            if text.strip():
                current_markdown.append(f"\n{'#' * level} {text.strip()}\n")
                
        elif block_type == "ListItem":
            text = html_to_text(html)
            if text.strip():
                current_markdown.append(f"- {text.strip()}\n")
        
        # Process children recursively
        children = getattr(block, "children", None)
        if children:
            for child in children:
                process_block(child, page_id, current_markdown)
    
    # Process each page
    children = getattr(rendered, "children", []) or []
    
    for page_idx, page in enumerate(children):
        page_id = page_idx + 1
        page_markdown: list[str] = []
        page_tables: list[str] = []
        page_figures: list[str] = []
        
        # Track tables/figures before processing
        tables_before = len(tables)
        figures_before = len(figures)
        
        process_block(page, page_id, page_markdown)
        
        # Get new tables/figures for this page
        page_tables = [t.block_id for t in tables[tables_before:]]
        page_figures = [f.block_id for f in figures[figures_before:]]
        
        markdown_content = "\n".join(page_markdown)
        word_count = len(markdown_content.split())
        
        pages.append(PageBlock(
            page_id=page_id,
            markdown_content=markdown_content,
            tables=page_tables,
            figures=page_figures,
            word_count=word_count,
        ))
    
    return pages, tables, figures, images_to_upload


def html_table_to_markdown(html: str) -> str:
    """Convert HTML table to Markdown format."""
    # Simplified conversion - in production, use a proper HTML parser
    # Remove HTML tags but preserve structure
    
    # Extract rows
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    
    if not rows:
        return html  # Return original if no table structure found
    
    md_rows = []
    for i, row in enumerate(rows):
        # Extract cells (th or td)
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.DOTALL | re.IGNORECASE)
        
        # Clean cell content
        cleaned_cells = []
        for cell in cells:
            # Remove HTML tags
            text = re.sub(r"<[^>]+>", "", cell)
            text = text.strip().replace("|", "\\|")
            cleaned_cells.append(text)
        
        if cleaned_cells:
            md_rows.append("| " + " | ".join(cleaned_cells) + " |")
            
            # Add separator after header row
            if i == 0:
                separator = "| " + " | ".join(["---"] * len(cleaned_cells)) + " |"
                md_rows.append(separator)
    
    return "\n".join(md_rows)


def html_to_text(html: str) -> str:
    """Extract text from HTML."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html)
    # Decode HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&amp;", "&")
    return text.strip()


def determine_header_level(html: str) -> int:
    """Determine header level from HTML."""
    match = re.search(r"<h(\d)", html, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 2  # Default to H2


def extract_caption_from_context(html: str) -> Optional[str]:
    """Try to extract a caption from surrounding HTML context."""
    # Look for caption-like patterns
    caption_patterns = [
        r"caption[^>]*>([^<]+)<",
        r"title[^>]*>([^<]+)<",
        r"<figcaption[^>]*>([^<]+)<",
    ]
    
    for pattern in caption_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def generate_table_footnote(table_markdown: str, table_number: int, page_number: int) -> str:
    """
    Use OpenAI to generate an intelligent footnote for a table.
    The footnote summarizes what the table contains and its key insights.
    """
    try:
        client = get_openai_client()
        
        prompt = f"""Analyze this table from page {page_number} of a document and generate a concise footnote (1-2 sentences) that:
1. Describes what data the table contains
2. Highlights any key figures or trends if visible

Table content:
{table_markdown[:2000]}  # Limit to avoid token overflow

Generate ONLY the footnote text, no labels or prefixes."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a document analyst. Generate concise, informative footnotes for tables in academic/policy documents."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.3,
        )
        
        footnote = response.choices[0].message.content.strip()
        logger.info(f"Generated footnote for Table {table_number}: {footnote[:50]}...")
        return footnote
        
    except Exception as e:
        logger.warning(f"Failed to generate AI footnote for table: {e}")
        # Fallback to basic description
        return f"Table {table_number} on page {page_number}."


def generate_figure_footnote(
    image_data: Optional[bytes],
    figure_number: int,
    page_number: int,
    context_text: str = "",
) -> str:
    """
    Use OpenAI Vision to generate an intelligent footnote for a figure/image.
    Describes what the image shows and its relevance.
    """
    try:
        client = get_openai_client()
        
        messages = [
            {"role": "system", "content": "You are a document analyst. Generate concise, informative footnotes for figures in academic/policy documents. Describe what the figure shows and any key insights."}
        ]
        
        if image_data:
            # Use vision model to analyze the image
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"This is Figure {figure_number} from page {page_number}. Generate a concise footnote (1-2 sentences) describing what this figure shows. Context from document: {context_text[:500]}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": "low"  # Use low detail to save tokens
                        }
                    }
                ]
            })
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=150,
                temperature=0.3,
            )
        else:
            # No image data, use context only
            messages.append({
                "role": "user",
                "content": f"Generate a concise footnote for Figure {figure_number} on page {page_number}. Context: {context_text[:500]}"
            })
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=100,
                temperature=0.3,
            )
        
        footnote = response.choices[0].message.content.strip()
        logger.info(f"Generated footnote for Figure {figure_number}: {footnote[:50]}...")
        return footnote
        
    except Exception as e:
        logger.warning(f"Failed to generate AI footnote for figure: {e}")
        # Fallback
        return f"Figure {figure_number} on page {page_number}."


def handler(event: dict, context: Any) -> dict:
    """
    Lambda handler for document conversion.
    
    Expected input (from Step Functions):
    {
        "ingestion_id": "ing-xxx",
        "document_id": "doc-xxx",
        "s3_key": "raw/ing-xxx/source.pdf",
        "s3_bucket": "vizonomy-raw-docs",
        "source_type": "pdf",
        "trace_id": "trace-xxx"
    }
    """
    start_time = datetime.now(timezone.utc)
    request_id = context.aws_request_id if context else str(uuid.uuid4())
    
    logger.set_request_id(request_id)
    logger.info("Marker converter Lambda invoked", extra={"event": event})
    
    try:
        # Parse input
        input_data = ConversionInput.model_validate(event)
        
        ingestion_id = input_data.ingestion_id
        document_id = input_data.document_id
        s3_bucket = input_data.s3_bucket
        s3_key = input_data.s3_key
        
        # Determine output prefix
        output_prefix = input_data.converted_key_prefix or f"converted/{ingestion_id}"
        
        # Create temp directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download source document
            source_ext = s3_key.rsplit(".", 1)[-1] if "." in s3_key else "pdf"
            local_source = os.path.join(temp_dir, f"source.{source_ext}")
            download_from_s3(s3_bucket, s3_key, local_source)
            
            # Convert with Marker
            logger.info(f"Converting document with Marker: {s3_key}")
            converter = get_converter()
            rendered = converter(local_source)
            
            # Extract text and images
            text, metadata_dict, images = text_from_rendered(rendered)
            
            # Extract structured blocks with footnotes
            pages, tables, figures, images_to_upload = extract_blocks_with_footnotes(
                rendered,
                ingestion_id,
                document_id,
            )
            
            # Create enhanced markdown with footnotes
            enhanced_markdown = create_enhanced_markdown(pages, tables, figures)
            
            # Upload markdown
            markdown_key = f"{output_prefix}/document.md"
            upload_to_s3(
                PROCESSED_BUCKET,
                markdown_key,
                enhanced_markdown,
                content_type="text/markdown",
            )
            
            # Create structured JSON
            structured_data = {
                "document_id": document_id,
                "ingestion_id": ingestion_id,
                "pages": [p.model_dump() for p in pages],
                "tables": [t.model_dump() for t in tables],
                "figures": [f.model_dump() for f in figures],
                "metadata": {
                    "total_pages": len(pages),
                    "total_tables": len(tables),
                    "total_figures": len(figures),
                    "total_words": sum(p.word_count for p in pages),
                    "source_key": s3_key,
                    "converted_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            
            # Upload structured JSON
            structured_json_key = f"{output_prefix}/structured.json"
            upload_to_s3(
                PROCESSED_BUCKET,
                structured_json_key,
                json.dumps(structured_data, indent=2),
                content_type="application/json",
            )
            
            # Upload images
            for image_key, image_data in images_to_upload.items():
                full_key = f"{output_prefix}/{image_key}"
                upload_to_s3(
                    PROCESSED_BUCKET,
                    full_key,
                    image_data,
                    content_type="image/png",
                )
            
            # Also upload any images from marker directly
            if images:
                for img_name, img_data in images.items():
                    if isinstance(img_data, bytes):
                        img_key = f"{output_prefix}/images/{img_name}"
                        upload_to_s3(
                            PROCESSED_BUCKET,
                            img_key,
                            img_data,
                            content_type="image/png",
                        )
            
            # Calculate processing time
            end_time = datetime.now(timezone.utc)
            processing_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # Build output
            output = ConversionOutput(
                ingestion_id=ingestion_id,
                document_id=document_id,
                markdown_key=markdown_key,
                structured_json_key=structured_json_key,
                pages=pages,
                tables=tables,
                figures=figures,
                total_pages=len(pages),
                total_tables=len(tables),
                total_figures=len(figures),
                metadata={
                    "processing_time_ms": processing_time_ms,
                    "source_type": input_data.source_type,
                    "trace_id": input_data.trace_id,
                },
                processing_time_ms=processing_time_ms,
            )
            
            logger.info(
                "Conversion complete",
                extra={
                    "pages": len(pages),
                    "tables": len(tables),
                    "figures": len(figures),
                    "processing_time_ms": processing_time_ms,
                },
            )
            
            return output.model_dump()
            
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise
    except ConversionError as e:
        logger.error(f"Conversion error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise ConversionError(f"Document conversion failed: {e}")


def create_enhanced_markdown(
    pages: list[PageBlock],
    tables: list[TableBlock],
    figures: list[FigureBlock],
) -> str:
    """
    Create an enhanced markdown document with footnotes appendix.
    """
    markdown_parts = []
    
    # Add document header
    markdown_parts.append("# Document\n\n")
    
    # Add page content
    for page in pages:
        markdown_parts.append(f"---\n\n## Page {page.page_id}\n\n")
        markdown_parts.append(page.markdown_content)
        markdown_parts.append("\n\n")
    
    # Add footnotes appendix for tables
    if tables:
        markdown_parts.append("\n---\n\n## Appendix: Tables\n\n")
        for table in tables:
            markdown_parts.append(f"### {table.footnote_ref}\n\n")
            markdown_parts.append(f"**AI Summary:** {table.caption}\n\n")
            markdown_parts.append(f"**Location:** Page {table.page_number}\n\n")
            markdown_parts.append("**Content:**\n\n")
            markdown_parts.append(table.markdown)
            markdown_parts.append("\n\n")
    
    # Add footnotes appendix for figures
    if figures:
        markdown_parts.append("\n---\n\n## Appendix: Figures\n\n")
        for figure in figures:
            markdown_parts.append(f"### {figure.footnote_ref}\n\n")
            markdown_parts.append(f"**AI Description:** {figure.caption}\n\n")
            markdown_parts.append(f"**Location:** Page {figure.page_number}\n\n")
            markdown_parts.append(f"**Image:** [{figure.footnote_ref}]({figure.image_key})\n\n")
    
    return "".join(markdown_parts)

