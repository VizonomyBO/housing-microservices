"""Ingestion Finalizer Lambda - Marks document as active"""
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context) -> dict:
    logger.info(f"Ingestion finalizer: {json.dumps(event)}")
    
    document_id = event.get("document_id")
    ingestion_id = event.get("ingestion_id")
    
    # TODO: Update document status to 'active' in database
    
    return {
        "statusCode": 200,
        "document_id": document_id,
        "ingestion_id": ingestion_id,
        "status": "completed",
        "message": "Document ingestion completed"
    }

