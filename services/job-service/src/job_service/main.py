"""Main FastAPI application for the job service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from job_service.jobs import JobResult, ReportPreGenerationJob
from job_service.scheduler import JobScheduler
from job_service.settings import Settings, load_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global instances (initialized in lifespan)
settings: Settings | None = None
scheduler: JobScheduler | None = None
report_job: ReportPreGenerationJob | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global settings, scheduler, report_job

    # Startup
    logger.info("Starting job service...")
    settings = load_settings()

    # Initialize job
    report_job = ReportPreGenerationJob(settings)

    # Initialize and start scheduler
    scheduler = JobScheduler(settings, report_job)
    scheduler.start()

    logger.info(f"Job service started on port {settings.http_port}")
    logger.info(
        f"Report regeneration scheduled for day {settings.schedule.day_of_month} "
        f"at {settings.schedule.hour:02d}:{settings.schedule.minute:02d}"
    )

    yield

    # Shutdown
    logger.info("Shutting down job service...")
    if scheduler:
        scheduler.shutdown()


app = FastAPI(
    title="Job Service",
    description="Scheduled job service for housing microservices",
    version="0.1.0",
    lifespan=lifespan,
)


# Response models
class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str


class JobInfo(BaseModel):
    id: str
    name: str
    next_run: str | None
    trigger: str


class SchedulerStatusResponse(BaseModel):
    status: str
    jobs: list[JobInfo]


class JobResultResponse(BaseModel):
    job_name: str
    started_at: str
    completed_at: str | None
    duration_seconds: float
    success: bool
    total_items: int
    succeeded_items: int
    failed_items: int
    skipped_items: int
    failed_details: list[dict]
    error_message: str | None


class TriggerResponse(BaseModel):
    message: str
    job_id: str


# Endpoints
@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="job-service",
        timestamp=datetime.now().isoformat(),
    )


@app.get("/v1/scheduler/status", response_model=SchedulerStatusResponse, tags=["scheduler"])
async def get_scheduler_status():
    """Get scheduler status and job information."""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    jobs = scheduler.get_jobs_info()
    return SchedulerStatusResponse(
        status="running",
        jobs=[JobInfo(**job) for job in jobs],
    )


@app.get("/v1/jobs/report-pregeneration/status", tags=["jobs"])
async def get_report_job_status():
    """Get the status of the report pre-generation job."""
    if not report_job:
        raise HTTPException(status_code=503, detail="Job not initialized")

    last_result = report_job.last_result
    return {
        "is_running": report_job.is_running,
        "last_result": _result_to_response(last_result) if last_result else None,
    }


@app.post("/v1/jobs/report-pregeneration/trigger", response_model=TriggerResponse, tags=["jobs"])
async def trigger_report_pregeneration(background_tasks: BackgroundTasks):
    """
    Manually trigger the report regeneration job.

    This will regenerate reports for priority countries (MEX, BRA, IDN, GHA, KEN, VNM)
    with skip_cache=True, overwriting existing cached reports.
    Reports expire 30 days after generation.
    """
    if not report_job:
        raise HTTPException(status_code=503, detail="Job not initialized")

    if report_job.is_running:
        raise HTTPException(status_code=409, detail="Job is already running")

    # Run in background
    background_tasks.add_task(report_job.run)

    return TriggerResponse(
        message="Job triggered successfully",
        job_id="report_pregeneration",
    )


@app.get("/v1/jobs/report-pregeneration/last-result", tags=["jobs"])
async def get_last_result():
    """Get the result of the last job execution."""
    if not report_job:
        raise HTTPException(status_code=503, detail="Job not initialized")

    last_result = report_job.last_result
    if not last_result:
        raise HTTPException(status_code=404, detail="No job result available")

    return _result_to_response(last_result)


def _result_to_response(result: JobResult) -> JobResultResponse:
    """Convert JobResult to response model."""
    return JobResultResponse(
        job_name=result.job_name,
        started_at=result.started_at.isoformat(),
        completed_at=result.completed_at.isoformat() if result.completed_at else None,
        duration_seconds=result.duration_seconds,
        success=result.success,
        total_items=result.total_items,
        succeeded_items=result.succeeded_items,
        failed_items=result.failed_items,
        skipped_items=result.skipped_items,
        failed_details=result.failed_details,
        error_message=result.error_message,
    )


__all__ = ["app"]
