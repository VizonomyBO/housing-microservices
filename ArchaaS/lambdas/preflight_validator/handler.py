"""
Preflight Validator Lambda - S3 Triggered

Triggered by S3 ObjectCreated events when a document is uploaded.

This Lambda:
1. Downloads the file from S3
2. Calculates SHA-256 hash
3. Checks for duplicate documents (same user + same hash)
4. If duplicate: marks document as DEDUPED
5. If new: starts the Step Function for processing
"""
import json
import os
import hashlib
import asyncio
import urllib.parse
from datetime import datetime, timezone
from typing import Any
from functools import wraps

import aioboto3

from db.repository import DocumentRepository
from db.models import DocumentStatus
from core.exceptions import DatabaseError
from core.logging import get_logger

logger = get_logger(__name__)

# Configuration
STEP_FUNCTION_ARN = os.environ.get("STEP_FUNCTION_ARN", "")
PROCESSED_BUCKET = os.environ.get("PROCESSED_ARTIFACTS_BUCKET", "")
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for streaming hash


def async_handler(f):
    """Decorator to run async handlers in Lambda."""
    @wraps(f)
    def wrapper(event, context):
        return asyncio.get_event_loop().run_until_complete(f(event, context))
    return wrapper


async def calculate_s3_hash(bucket: str, key: str) -> tuple[str, int]:
    """
    Download file from S3 and calculate SHA-256 hash.
    Returns (hash_hex, file_size_bytes)
    """
    session = aioboto3.Session()
    hasher = hashlib.sha256()
    
    async with session.client("s3") as s3:
        response = await s3.get_object(Bucket=bucket, Key=key)
        
        # Read the entire body (aioboto3 doesn't support chunked streaming)
        body = await response["Body"].read()
        hasher.update(body)
        total_size = len(body)
    
    return hasher.hexdigest(), total_size


async def start_step_function(document_id: str, document_data: dict) -> str:
    """Start the document ingestion Step Function."""
    if not STEP_FUNCTION_ARN:
        logger.warning("STEP_FUNCTION_ARN not configured, skipping Step Function start")
        return None
    
    session = aioboto3.Session()
    
    async with session.client("stepfunctions") as sfn:
        response = await sfn.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=f"doc-{document_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            input=json.dumps({
                "document_id": document_id,
                "bucket": document_data.get("bucket"),
                "key": document_data.get("key"),
                "content_hash": document_data.get("content_hash"),
                "source_type": document_data.get("source_type"),
                "owner_user_id": document_data.get("owner_user_id"),
                "canonical_name": document_data.get("canonical_name"),
            }),
        )
        
        execution_arn = response["executionArn"]
        logger.info(f"Started Step Function execution: {execution_arn}")
        return execution_arn


def extract_document_id_from_key(key: str) -> str:
    """Extract document_id from S3 key like 'raw/{document_id}/source.pdf'"""
    parts = key.split("/")
    if len(parts) >= 2:
        return parts[1]  # raw/{document_id}/source.ext
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
    2. Calculate SHA-256 hash
    3. Look up document record
    4. Check for duplicates
    5. Update document and start Step Function or mark as DEDUPED
    """
    logger.info("Preflight validator triggered", extra={"event": json.dumps(event)})
    
    # Handle S3 event records
    records = event.get("Records", [])
    if not records:
        logger.warning("No records in event")
        return {"statusCode": 200, "body": "No records to process"}
    
    results = []
    
    for record in records:
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
            
            # Calculate hash
            logger.info(f"Calculating hash for document {document_id}")
            content_hash, file_size = await calculate_s3_hash(bucket, key)
            logger.info(f"Hash calculated: {content_hash[:16]}... ({file_size} bytes)")
            
            # Get document record
            repository = DocumentRepository()
            document = await repository.get_document_by_id(document_id)
            
            if not document:
                logger.error(f"Document {document_id} not found in database")
                continue
            
            owner_user_id = document.get("owner_user_id")
            
            # Check for duplicates (same owner + same hash)
            if owner_user_id:
                existing = await repository.find_by_owner_and_hash(owner_user_id, content_hash)
                
                if existing and str(existing["id"]) != document_id:
                    # Duplicate found!
                    logger.info(
                        f"Duplicate detected: {document_id} matches {existing['id']}",
                        extra={"content_hash": content_hash}
                    )
                    
                    # Update current document as DEDUPED
                    # Parse existing metadata (could be dict or JSON string)
                    existing_metadata = document.get("metadata", {})
                    if isinstance(existing_metadata, str):
                        try:
                            existing_metadata = json.loads(existing_metadata) if existing_metadata else {}
                        except:
                            existing_metadata = {}
                    elif existing_metadata is None:
                        existing_metadata = {}
                    
                    await repository.update_document_status(
                        document_id,
                        status="DEDUPED",
                        content_hash=content_hash,
                        extra_fields={
                            "metadata": json.dumps({
                                **existing_metadata,
                                "deduped_from": str(existing["id"]),
                                "dedup_detected_at": datetime.now(timezone.utc).isoformat(),
                            })
                        }
                    )
                    
                    # Delete the duplicate file from S3 to save space
                    session = aioboto3.Session()
                    async with session.client("s3") as s3:
                        await s3.delete_object(Bucket=bucket, Key=key)
                        logger.info(f"Deleted duplicate file: s3://{bucket}/{key}")
                    
                    results.append({
                        "document_id": document_id,
                        "status": "DEDUPED",
                        "deduped_from": str(existing["id"]),
                    })
                    continue
            
            # Not a duplicate - update document with hash and start processing
            await repository.update_document_status(
                document_id,
                status="PENDING_VALIDATION",
                content_hash=content_hash,
                extra_fields={
                    "byte_size": file_size,
                    "ingestion_started_at": datetime.now(timezone.utc),
                }
            )
            
            # Start Step Function for processing
            execution_arn = await start_step_function(
                document_id,
                {
                    "bucket": bucket,
                    "key": key,
                    "content_hash": content_hash,
                    "source_type": source_type,
                    "owner_user_id": owner_user_id,
                    "canonical_name": document.get("canonical_name"),
                }
            )
            
            results.append({
                "document_id": document_id,
                "status": "PROCESSING",
                "content_hash": content_hash,
                "execution_arn": execution_arn,
            })
            
        except Exception as e:
            logger.error(f"Error processing record: {e}", exc_info=True)
            results.append({
                "error": str(e),
            })
    
    return {
        "statusCode": 200,
        "body": json.dumps({"results": results}),
    }
