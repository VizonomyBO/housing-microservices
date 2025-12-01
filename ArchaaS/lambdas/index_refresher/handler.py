"""Index Refresher Lambda - Placeholder"""
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context) -> dict:
    logger.info(f"Index refresher (placeholder): {json.dumps(event)}")
    return {
        "statusCode": 200,
        "document_id": event.get("document_id"),
        "ingestion_id": event.get("ingestion_id"),
        "message": "Index refresh disabled (Task 2.3)"
    }

