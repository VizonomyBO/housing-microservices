"""Ingestion job and document management utilities."""

import os
import uuid
from datetime import UTC, datetime
from uuid import UUID

# Import from shared_data_layer (available via Lambda layer)
from shared_data_layer.db.models.documents import (
    Artifact,
    Document,
    IngestionJob,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# Valid stages as defined in schema constraints
VALID_STAGES = ["preflight", "convert", "chunk", "embed", "index", "activate"]

# Valid document statuses
VALID_STATUSES = ["registered", "ingesting", "active", "failed", "archived"]

# Valid ingestion job statuses
VALID_JOB_STATUSES = ["pending", "running", "succeeded", "failed", "canceled"]


class IngestionJobManager:
    """
    Manages IngestionJob records throughout the pipeline.

    Usage:
        async with get_async_session() as session:
            manager = IngestionJobManager(session)
            job = await manager.start_job(document_id, "preflight", trace_id)
            # ... do work ...
            await manager.complete_job(job.id)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_job(
        self,
        document_id: UUID,
        stage: str,
        trace_id: str | None = None,
        worker: str | None = None,
    ) -> IngestionJob:
        """
        Start a new ingestion job for a stage.

        If a pending/running job exists for this stage, increments attempt counter.
        """
        if stage not in VALID_STAGES:
            raise ValueError(f"Invalid stage: {stage}. Must be one of {VALID_STAGES}")

        # Check for existing job
        stmt = select(IngestionJob).where(
            IngestionJob.document_id == document_id,
            IngestionJob.stage == stage,
            IngestionJob.status.in_(["pending", "running"]),
        )
        result = await self.session.execute(stmt)
        existing_job = result.scalar_one_or_none()

        if existing_job:
            # Increment attempt counter
            existing_job.attempt += 1
            existing_job.status = "running"
            existing_job.started_at = datetime.now(UTC)
            existing_job.worker = worker or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
            if trace_id:
                existing_job.trace_id = UUID(trace_id) if isinstance(trace_id, str) else trace_id
            await self.session.flush()
            return existing_job

        # Create new job
        job = IngestionJob(
            id=uuid.uuid4(),
            document_id=document_id,
            stage=stage,
            status="running",
            attempt=1,
            worker=worker or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"),
            trace_id=UUID(trace_id) if trace_id else None,
            started_at=datetime.now(UTC),
        )
        self.session.add(job)
        await self.session.flush()

        return job

    async def complete_job(
        self,
        job_id: UUID,
        metadata: dict | None = None,
    ) -> None:
        """Mark a job as succeeded."""
        stmt = (
            update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(
                status="succeeded",
                completed_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)

    async def fail_job(
        self,
        job_id: UUID,
        error_code: str,
        error_message: str,
        error_details: dict | None = None,
    ) -> None:
        """Mark a job as failed with error information."""
        last_error = {
            "code": error_code,
            "message": error_message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if error_details:
            last_error["details"] = error_details

        stmt = (
            update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(
                status="failed",
                completed_at=datetime.now(UTC),
                last_error=last_error,
            )
        )
        await self.session.execute(stmt)

    async def get_job(self, job_id: UUID) -> IngestionJob | None:
        """Get a job by ID."""
        return await self.session.get(IngestionJob, job_id)


async def update_document_stage(
    session: AsyncSession,
    document_id: UUID,
    stage: str,
    status: str | None = None,
) -> None:
    """
    Update the document's ingestion stage and optionally status.

    Args:
        session: Database session
        document_id: Document ID
        stage: New ingestion stage
        status: Optional new document status
    """
    if stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage: {stage}")

    values = {"ingestion_stage": stage}

    if status:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        values["status"] = status

    # Set ingestion_started_at on first stage
    if stage == "preflight":
        values["ingestion_started_at"] = datetime.now(UTC)

    # Set ingestion_completed_at on final stage
    if stage == "activate" and status == "active":
        values["ingestion_completed_at"] = datetime.now(UTC)

    stmt = update(Document).where(Document.id == document_id).values(**values)
    await session.execute(stmt)


async def create_artifact_record(
    session: AsyncSession,
    document_id: UUID,
    artifact_type: str,
    s3_key: str,
    s3_bucket: str,
    byte_size: int | None = None,
    metadata: dict | None = None,
) -> Artifact:
    """
    Create an artifact record in the database.

    Args:
        session: Database session
        document_id: Document ID
        artifact_type: Type of artifact (markdown, structured_json, table, figure, chunk_manifest)
        s3_key: S3 object key
        s3_bucket: S3 bucket name
        byte_size: Optional file size in bytes
        metadata: Optional additional metadata
    """
    artifact = Artifact(
        id=uuid.uuid4(),
        document_id=document_id,
        artifact_type=artifact_type,
        s3_uri=f"s3://{s3_bucket}/{s3_key}",
        byte_size=byte_size,
        metadata_=metadata,
    )
    session.add(artifact)
    await session.flush()

    return artifact
