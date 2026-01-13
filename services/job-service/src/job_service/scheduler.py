"""APScheduler setup and management."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from job_service.jobs import ReportPreGenerationJob
    from job_service.settings import Settings

logger = logging.getLogger(__name__)


class JobScheduler:
    """Manages scheduled jobs using APScheduler."""

    def __init__(self, settings: Settings, report_job: ReportPreGenerationJob):
        self.settings = settings
        self.report_job = report_job
        self.scheduler = AsyncIOScheduler()
        self._setup_jobs()

    def _setup_jobs(self) -> None:
        """Configure scheduled jobs."""
        schedule = self.settings.schedule

        # Report pre-generation: runs on specified day of month
        self.scheduler.add_job(
            self._run_report_pregeneration,
            CronTrigger(
                day=schedule.day_of_month,
                hour=schedule.hour,
                minute=schedule.minute,
            ),
            id="report_pregeneration",
            name="Report Pre-Generation",
            replace_existing=True,
            max_instances=1,  # Prevent overlapping runs
        )

        logger.info(
            f"Scheduled report pre-generation: day={schedule.day_of_month}, "
            f"hour={schedule.hour}, minute={schedule.minute}"
        )

    async def _run_report_pregeneration(self) -> None:
        """Wrapper to run the report pre-generation job."""
        logger.info("Scheduler triggered: report_pregeneration")
        try:
            result = await self.report_job.run()
            if result.success:
                logger.info(
                    f"Scheduled job completed successfully: "
                    f"{result.succeeded_items}/{result.total_items} reports generated"
                )
            else:
                logger.error(
                    f"Scheduled job completed with failures: "
                    f"{result.failed_items}/{result.total_items} failed"
                )
        except Exception as e:
            logger.exception(f"Scheduled job failed: {e}")

    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Job scheduler started")

        # Run on startup if configured
        if self.settings.schedule.run_on_startup:
            logger.info("Run-on-startup enabled, triggering job...")
            asyncio.create_task(self._run_report_pregeneration())

    def shutdown(self) -> None:
        """Shutdown the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Job scheduler stopped")

    def get_jobs_info(self) -> list[dict]:
        """Get information about scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": next_run.isoformat() if next_run else None,
                    "trigger": str(job.trigger),
                }
            )
        return jobs

    def trigger_job(self, job_id: str) -> bool:
        """Manually trigger a job by ID."""
        job = self.scheduler.get_job(job_id)
        if job:
            logger.info(f"Manually triggering job: {job_id}")
            self.scheduler.modify_job(job_id, next_run_time=datetime.now())
            return True
        return False


__all__ = ["JobScheduler"]
