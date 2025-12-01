"""
Preflight Validator Lambda - S3 Triggered

Triggered by S3 ObjectCreated events when a document is uploaded.

This Lambda:
1. Downloads the file from S3
2. Performs MIME type sniffing and validation
3. Calculates SHA-256 hash
4. Checks for duplicate documents (same user + same hash)
5. Creates/updates IngestionJob records
6. If duplicate: marks document as archived (deduped)
7. If new: starts the Step Function for processing
8. Emits progress events to EventBridge
"""
import json
import os
import hashlib
import asyncio
import tempfile
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Optional
from functools import wraps
from uuid import UUID

import aioboto3

# Common utilities (from common/ directory or Lambda layer)
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.db import get_async_session
from common.events import emit_progress_event, emit_failure_event
from common.ingestion import (
    IngestionJobManager,
    update_document_stage,
    VALID_STAGES,
)
from common.mime import detect_mime_type, validate_mime_type

# shared_data_layer models (from Lambda layer)
from shared_data_layer.db.models.documents import Document, IngestionJob
from shared_data_layer.repositories.documents import DocumentRepository

from core.logging import get_logger
from core.exceptions import (
    ValidationError,
    DuplicateDocumentError,
    DatabaseError,
)

logger = get_logger(__name__)

# Configuration
STEP_FUNCTION_ARN = os.environ.get("STEP_FUNCTION_ARN", "")
PROCESSED_BUCKET = os.environ.get("PROCESSED_ARTIFACTS_BUCKET", "")
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for streaming hash


def async_handler(f):
    """Decorator to run async handlers in Lambda."""
    @wraps(f)
    def wrapper(event, context):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(f(event, context))
        finally:
            loop.close()
    return wrapper


async def download_and_analyze_file(
    bucket: str,
    key: str,
) -> tuple[str, int, str, str]:
    """
    Download file from S3, calculate hash and detect MIME type.
    
    Returns:
        (content_hash, file_size, mime_type, detection_method)
    """
    session = aioboto3.Session()
    hasher = hashlib.sha256()
    
    async with session.client("s3") as s3:
        response = await s3.get_object(Bucket=bucket, Key=key)
        body = await response["Body"].read()
        
        # Calculate hash
        hasher.update(body)
        content_hash = hasher.hexdigest()
        file_size = len(body)
        
        # Detect MIME type from content
        mime_type, detection_method = detect_mime_type(
            file_content=body[:8192],  # First 8KB for magic number detection
            filename=key.split("/")[-1],
        )
    
    return content_hash, file_size, mime_type, detection_method


async def start_step_function(
    document_id: str,
    ingestion_job_id: str,
    document_data: dict,
) -> Optional[str]:
    """Start the document ingestion Step Function."""
    if not STEP_FUNCTION_ARN:
        logger.warning("STEP_FUNCTION_ARN not configured, skipping Step Function start")
        return None
    
    session = aioboto3.Session()
    
    async with session.client("stepfunctions") as sfn:
        response = await sfn.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=f"doc-{document_id[:8]}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            input=json.dumps({
                "document_id": document_id,
                "ingestion_id": ingestion_job_id,
                "bucket": document_data.get("bucket"),
                "key": document_data.get("key"),
                "content_hash": document_data.get("content_hash"),
                "source_type": document_data.get("source_type"),
                "owner_user_id": str(document_data.get("owner_user_id")) if document_data.get("owner_user_id") else None,
                "canonical_name": document_data.get("canonical_name"),
                "country_code": document_data.get("country_code"),
                "language": document_data.get("language"),
                "access_scope": document_data.get("access_scope"),
                "trace_id": document_data.get("trace_id"),
            }),
        )
        
        execution_arn = response["executionArn"]
        logger.info(f"Started Step Function execution: {execution_arn}")
        return execution_arn


def extract_document_id_from_key(key: str) -> str:
    """Extract document_id from S3 key like 'raw/{document_id}/source.pdf'"""
    parts = key.split("/")
    if len(parts) >= 2:
        return parts[1]
    raise ValueError(f"Cannot extract document_id from key: {key}")


def extract_source_type_from_key(key: str) -> str:
    """Extract file extension from S3 key."""
    filename = key.split("/")[-1]
    if "." in filename:
        return filename.split(".")[-1].lower()
    return "unknown"


@async_handler
async def handler(event: dict, context: Any) -> dict:
    """
    Main Lambda handler - triggered by S3 ObjectCreated events.
    
    Flow:
    1. Get S3 object info from event
    2. Download file and perform analysis (hash, MIME type)
    3. Validate MIME type
    4. Look up document record via shared_data_layer
    5. Create IngestionJob record
    6. Check for duplicates
    7. Update document and start Step Function or mark as deduped
    8. Emit progress events
    """
    request_id = getattr(context, "aws_request_id", None) or "local-test"
    logger.info("Preflight validator triggered", extra={"request_id": request_id})
    
    # Handle S3 event records
    records = event.get("Records", [])
    if not records:
        logger.warning("No records in event")
        return {"statusCode": 200, "body": "No records to process"}
    
    results = []
    
    for record in records:
        document_id = None
        ingestion_job_id = None
        
        try:
            # Extract S3 info
            s3_info = record.get("s3", {})
            bucket = s3_info.get("bucket", {}).get("name")
            key = urllib.parse.unquote_plus(s3_info.get("object", {}).get("key", ""))
            
            if not bucket or not key:
                logger.error("Missing bucket or key in S3 event")
                continue
            
            logger.info(f"Processing S3 object: s3://{bucket}/{key}")
            
            # Extract document ID from key
            try:
                document_id = extract_document_id_from_key(key)
            except ValueError as e:
                logger.error(f"Failed to extract document_id: {e}")
                continue
            
            source_type = extract_source_type_from_key(key)
            
            # Download and analyze file
            logger.info(f"Analyzing document {document_id}")
            content_hash, file_size, mime_type, detection_method = await download_and_analyze_file(
                bucket, key
            )
            logger.info(
                f"Analysis complete: hash={content_hash[:16]}..., "
                f"size={file_size}, mime={mime_type} ({detection_method})"
            )
            
            # Validate MIME type
            is_valid, error_msg = validate_mime_type(mime_type)
            if not is_valid:
                logger.error(f"MIME validation failed: {error_msg}")
                await emit_failure_event(
                    ingestion_id=document_id,
                    document_id=document_id,
                    failed_stage="preflight",
                    error_code="INVALID_MIME_TYPE",
                    error_message=error_msg,
                    trace_id=request_id,
                )
                results.append({
                    "document_id": document_id,
                    "status": "FAILED",
                    "error": error_msg,
                })
                continue
            
            # Use shared_data_layer for database operations
            async with get_async_session() as session:
                # Emit progress event: preflight started
                await emit_progress_event(
                    ingestion_id=document_id,
                    document_id=document_id,
                    stage="preflight",
                    status="started",
                    trace_id=request_id,
                )
                
                # Get document record
                document = await session.get(Document, UUID(document_id))
                
                if not document:
                    logger.error(f"Document {document_id} not found in database")
                    await emit_failure_event(
                        ingestion_id=document_id,
                        document_id=document_id,
                        failed_stage="preflight",
                        error_code="DOCUMENT_NOT_FOUND",
                        error_message=f"Document {document_id} not found",
                        trace_id=request_id,
                    )
                    continue
                
                owner_user_id = document.owner_user_id
                
                # Create IngestionJob record
                job_manager = IngestionJobManager(session)
                job = await job_manager.start_job(
                    document_id=UUID(document_id),
                    stage="preflight",
                    trace_id=request_id,
                )
                ingestion_job_id = str(job.id)
                logger.info(f"Created IngestionJob: {ingestion_job_id}")
                
                # Update document stage to preflight
                await update_document_stage(
                    session,
                    UUID(document_id),
                    stage="preflight",
                    status="ingesting",
                )
                
                # Check for duplicates (same owner + same hash, excluding current doc)
                if owner_user_id:
                    from sqlalchemy import select
                    from shared_data_layer.db.models import Document as SDLDocument
                    
                    stmt = select(SDLDocument).where(
                        SDLDocument.owner_user_id == owner_user_id,
                        SDLDocument.content_hash == content_hash,
                        SDLDocument.id != UUID(document_id),  # Exclude current document
                    )
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()
                    
                    if existing:
                        # Duplicate found!
                        logger.info(
                            f"Duplicate detected: {document_id} matches {existing.id}",
                            extra={"content_hash": content_hash}
                        )
                        
                        # Mark current document as archived (deduped)
                        document.status = "archived"
                        document.content_hash = content_hash
                        document.metadata_ = {
                            **(document.metadata_ or {}),
                            "deduped_from": str(existing.id),
                            "dedup_detected_at": datetime.now(timezone.utc).isoformat(),
                        }
                        
                        # Mark job as succeeded (dedup is a success case)
                        await job_manager.complete_job(job.id)
                        
                        # Commit the transaction
                        await session.commit()
                        
                        # Delete the duplicate file from S3 to save space
                        s3_session = aioboto3.Session()
                        async with s3_session.client("s3") as s3:
                            await s3.delete_object(Bucket=bucket, Key=key)
                            logger.info(f"Deleted duplicate file: s3://{bucket}/{key}")
                        
                        # Emit progress event: preflight completed (dedup)
                        await emit_progress_event(
                            ingestion_id=document_id,
                            document_id=document_id,
                            stage="preflight",
                            status="completed",
                            metadata={"result": "deduplicated", "deduped_from": str(existing.id)},
                            trace_id=request_id,
                        )
                        
                        results.append({
                            "document_id": document_id,
                            "ingestion_job_id": ingestion_job_id,
                            "status": "DEDUPED",
                            "deduped_from": str(existing.id),
                        })
                        continue
                
                # Not a duplicate - update document and prepare for processing
                document.content_hash = content_hash
                document.byte_size = file_size
                document.status = "ingesting"
                document.ingestion_started_at = datetime.now(timezone.utc)
                
                # Commit the transaction
                await session.commit()
                
                # Start Step Function for processing (convert, chunk, embed, etc.)
                execution_arn = await start_step_function(
                    document_id,
                    ingestion_job_id,
                    {
                        "bucket": bucket,
                        "key": key,
                        "content_hash": content_hash,
                        "source_type": source_type,
                        "owner_user_id": owner_user_id,
                        "canonical_name": document.canonical_name,
                        "country_code": document.country_code,
                        "language": document.language,
                        "access_scope": document.access_scope,
                        "trace_id": request_id,
                    }
                )
                
                # Mark preflight job as complete
                async with get_async_session() as session2:
                    job_manager2 = IngestionJobManager(session2)
                    await job_manager2.complete_job(UUID(ingestion_job_id))
                    await session2.commit()
                
                # Emit progress event: preflight completed
                await emit_progress_event(
                    ingestion_id=document_id,
                    document_id=document_id,
                    stage="preflight",
                    status="completed",
                    metadata={
                        "content_hash": content_hash,
                        "file_size": file_size,
                        "mime_type": mime_type,
                    },
                    trace_id=request_id,
                )
                
                results.append({
                    "document_id": document_id,
                    "ingestion_job_id": ingestion_job_id,
                    "status": "PROCESSING",
                    "content_hash": content_hash,
                    "execution_arn": execution_arn,
                })
                
        except Exception as e:
            logger.error(f"Error processing record: {e}", exc_info=True)
            
            # Emit failure event
            if document_id:
                await emit_failure_event(
                    ingestion_id=document_id,
                    document_id=document_id,
                    failed_stage="preflight",
                    error_code="PREFLIGHT_ERROR",
                    error_message=str(e),
                    trace_id=request_id,
                )
                
                # Mark job as failed if we created one
                if ingestion_job_id:
                    try:
                        async with get_async_session() as session:
                            job_manager = IngestionJobManager(session)
                            await job_manager.fail_job(
                                UUID(ingestion_job_id),
                                error_code="PREFLIGHT_ERROR",
                                error_message=str(e),
                            )
                            await session.commit()
                    except Exception:
                        pass
            
            results.append({
                "document_id": document_id,
                "error": str(e),
            })
    
    return {
        "statusCode": 200,
        "body": json.dumps({"results": results}),
    }
