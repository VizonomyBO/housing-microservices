"""
Figure Captioner Lambda - Placeholder (no image captions without ML)
"""

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context) -> dict:
    """Pass-through - no figure captioning without ML models."""
    logger.info(f"Figure captioner (placeholder): {json.dumps(event)}")

    return {
        "statusCode": 200,
        "document_id": event.get("document_id"),
        "ingestion_id": event.get("ingestion_id"),
        "figures_processed": 0,
        "message": "Figure captioning disabled (requires ML models)",
    }
