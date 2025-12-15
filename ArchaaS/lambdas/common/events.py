"""EventBridge event emission for ingestion progress tracking."""

import json
import os
from datetime import UTC, datetime

import boto3

# Event bus configuration
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "vizonomy-ingestion-events")
EVENT_SOURCE = "vizonomy.ingestion"

# Boto3 client (reused across Lambda invocations)
_eventbridge_client = None


def get_eventbridge_client():
    """Get or create EventBridge client."""
    global _eventbridge_client
    if _eventbridge_client is None:
        _eventbridge_client = boto3.client("events")
    return _eventbridge_client


async def emit_progress_event(
    ingestion_id: str,
    document_id: str,
    stage: str,
    status: str,
    percent_complete: int | None = None,
    metadata: dict | None = None,
    trace_id: str | None = None,
) -> None:
    """
    Emit a progress event to EventBridge.

    Args:
        ingestion_id: The ingestion job ID
        document_id: The document being processed
        stage: Current stage (preflight, convert, chunk, embed, index, activate)
        status: Status of the stage (started, completed, failed)
        percent_complete: Optional progress percentage (0-100)
        metadata: Optional additional metadata
        trace_id: Optional trace ID for correlation
    """
    client = get_eventbridge_client()

    detail = {
        "ingestion_id": ingestion_id,
        "document_id": document_id,
        "stage": stage,
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if percent_complete is not None:
        detail["percent_complete"] = percent_complete

    if trace_id:
        detail["trace_id"] = trace_id

    if metadata:
        detail["metadata"] = metadata

    try:
        client.put_events(
            Entries=[
                {
                    "Source": EVENT_SOURCE,
                    "DetailType": "ingestion.progress",
                    "Detail": json.dumps(detail),
                    "EventBusName": EVENT_BUS_NAME,
                }
            ]
        )
    except Exception as e:
        # Log but don't fail the Lambda on event emission errors
        print(f"Warning: Failed to emit progress event: {e}")


async def emit_completion_event(
    ingestion_id: str,
    document_id: str,
    content_hash: str,
    access_scope: str,
    chunk_count: int,
    execution_arn: str | None = None,
    trace_id: str | None = None,
) -> None:
    """
    Emit a completion event to EventBridge.

    This is emitted when the entire ingestion pipeline completes successfully.
    """
    client = get_eventbridge_client()

    detail = {
        "ingestion_id": ingestion_id,
        "document_id": document_id,
        "content_hash": content_hash,
        "access_scope": access_scope,
        "chunk_count": chunk_count,
        "status": "completed",
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if execution_arn:
        detail["execution_arn"] = execution_arn

    if trace_id:
        detail["trace_id"] = trace_id

    try:
        client.put_events(
            Entries=[
                {
                    "Source": EVENT_SOURCE,
                    "DetailType": "ingestion.completed",
                    "Detail": json.dumps(detail),
                    "EventBusName": EVENT_BUS_NAME,
                }
            ]
        )
    except Exception as e:
        print(f"Warning: Failed to emit completion event: {e}")


async def emit_failure_event(
    ingestion_id: str,
    document_id: str,
    failed_stage: str,
    error_code: str,
    error_message: str,
    will_retry: bool = False,
    execution_arn: str | None = None,
    trace_id: str | None = None,
) -> None:
    """
    Emit a failure event to EventBridge.

    This is emitted when a stage fails and won't be retried.
    """
    client = get_eventbridge_client()

    detail = {
        "ingestion_id": ingestion_id,
        "document_id": document_id,
        "failed_stage": failed_stage,
        "error_code": error_code,
        "error_message": error_message,
        "will_retry": will_retry,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if execution_arn:
        detail["execution_arn"] = execution_arn

    if trace_id:
        detail["trace_id"] = trace_id

    try:
        client.put_events(
            Entries=[
                {
                    "Source": EVENT_SOURCE,
                    "DetailType": "ingestion.failed",
                    "Detail": json.dumps(detail),
                    "EventBusName": EVENT_BUS_NAME,
                }
            ]
        )
    except Exception as e:
        print(f"Warning: Failed to emit failure event: {e}")
