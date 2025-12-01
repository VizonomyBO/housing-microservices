"""Embedding Writer Lambda - Placeholder"""
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context) -> dict:
    logger.info(f"Embedding writer (placeholder): {json.dumps(event)}")
    return {
        "statusCode": 200,
        "document_id": event.get("document_id"),
        "ingestion_id": event.get("ingestion_id"),
        "embeddings_written": 0,
        "message": "Embedding disabled (Task 2.3)"
    }

