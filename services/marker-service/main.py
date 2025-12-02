"""
Marker PDF Conversion Microservice

Converts PDFs to Markdown with AI-powered footnotes for tables and images.
"""
import os
import tempfile
import logging
from typing import Optional
from uuid import uuid4

import boto3
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
import openai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Marker PDF Converter", version="1.0.0")

# Initialize models on startup (cached for subsequent requests)
models = None

# Configuration
S3_RAW_BUCKET = os.environ.get("RAW_DOCUMENTS_BUCKET", "vizonomy-raw-docs-dev")
S3_PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "vizonomy-processed-dev")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY


class ConversionRequest(BaseModel):
    document_id: str
    bucket: str
    key: str
    content_hash: str
    source_type: str = "pdf"
    owner_user_id: Optional[str] = None
    country_code: Optional[str] = None
    trace_id: Optional[str] = None


class ConversionResponse(BaseModel):
    document_id: str
    status: str
    markdown_key: Optional[str] = None
    metadata_key: Optional[str] = None
    figures_prefix: Optional[str] = None
    tables_count: int = 0
    figures_count: int = 0
    error: Optional[str] = None


@app.on_event("startup")
async def load_models():
    """Load Marker models on startup."""
    global models
    logger.info("Loading Marker models (this may take a few minutes on first run)...")
    try:
        models = create_model_dict()
        logger.info("Marker models loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load models: {e}")
        models = None


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "models_loaded": models is not None
    }


@app.post("/convert", response_model=ConversionResponse)
async def convert_document(request: ConversionRequest):
    """Convert a PDF document to Markdown with footnotes."""
    global models
    
    if models is None:
        raise HTTPException(status_code=503, detail="Models not loaded yet")
    
    s3 = boto3.client("s3")
    
    try:
        # Download PDF from S3
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            s3.download_file(request.bucket, request.key, tmp.name)
            pdf_path = tmp.name
        
        logger.info(f"Converting document {request.document_id}")
        
        # Convert with Marker
        converter = PdfConverter(artifact_dict=models)
        rendered = converter(pdf_path)
        
        # Extract markdown and metadata
        markdown_content = rendered.markdown
        
        # Count tables and figures
        tables_count = markdown_content.count("|") // 10  # Rough estimate
        figures_count = markdown_content.count("![")
        
        # Generate footnotes for tables using OpenAI (if configured)
        if OPENAI_API_KEY and (tables_count > 0 or figures_count > 0):
            markdown_content = await add_ai_footnotes(markdown_content, request.document_id)
        
        # Upload results to S3
        output_prefix = f"processed/{request.document_id}"
        
        # Upload markdown
        markdown_key = f"{output_prefix}/content.md"
        s3.put_object(
            Bucket=S3_PROCESSED_BUCKET,
            Key=markdown_key,
            Body=markdown_content.encode("utf-8"),
            ContentType="text/markdown"
        )
        
        # Upload metadata
        metadata_key = f"{output_prefix}/metadata.json"
        import json
        metadata = {
            "document_id": request.document_id,
            "content_hash": request.content_hash,
            "tables_count": tables_count,
            "figures_count": figures_count,
            "source_type": request.source_type,
            "country_code": request.country_code,
        }
        s3.put_object(
            Bucket=S3_PROCESSED_BUCKET,
            Key=metadata_key,
            Body=json.dumps(metadata).encode("utf-8"),
            ContentType="application/json"
        )
        
        # Clean up
        os.unlink(pdf_path)
        
        logger.info(f"Conversion complete for {request.document_id}")
        
        return ConversionResponse(
            document_id=request.document_id,
            status="success",
            markdown_key=markdown_key,
            metadata_key=metadata_key,
            figures_prefix=f"{output_prefix}/figures/",
            tables_count=tables_count,
            figures_count=figures_count,
        )
        
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        return ConversionResponse(
            document_id=request.document_id,
            status="failed",
            error=str(e)
        )


async def add_ai_footnotes(markdown: str, document_id: str) -> str:
    """Add AI-generated footnotes for tables and figures."""
    if not OPENAI_API_KEY:
        return markdown
    
    try:
        client = openai.OpenAI()
        
        # Simple prompt to summarize tables
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a document analyst. Add brief footnotes after each table summarizing its key data points. Keep footnotes concise (1-2 sentences)."
                },
                {
                    "role": "user", 
                    "content": f"Add footnotes to summarize tables in this document:\n\n{markdown[:8000]}"
                }
            ],
            max_tokens=2000
        )
        
        return response.choices[0].message.content or markdown
        
    except Exception as e:
        logger.warning(f"Failed to add AI footnotes: {e}")
        return markdown


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)

