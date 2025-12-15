"""
Table Normalizer Lambda - Normalizes extracted tables.

Simplified version - just passes through since pdfplumber already extracts tables.
"""

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context) -> dict:
    """Process tables - currently pass-through since tables handled in conversion."""
    logger.info(f"Table normalizer: {json.dumps(event)}")

    document_id = event.get("document_id")
    ingestion_id = event.get("ingestion_id")
    convert_result = event.get("convert_result", {})

    return {
        "statusCode": 200,
        "document_id": document_id,
        "ingestion_id": ingestion_id,
        "tables_processed": convert_result.get("tables_count", 0),
        "message": "Tables already processed during conversion",
    }
