"""Job definitions for scheduled tasks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dateutil.relativedelta import relativedelta

from job_service.clients import AgentApiClient, AuthClient
from job_service.settings import Settings

logger = logging.getLogger(__name__)


def get_next_month() -> str:
    """Get the next month in YYYY-MM format."""
    next_month = datetime.now() + relativedelta(months=1)
    return next_month.strftime("%Y-%m")


@dataclass
class JobResult:
    """Result of a job execution."""

    job_name: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    total_items: int = 0
    succeeded_items: int = 0
    failed_items: int = 0
    failed_details: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


class ReportPreGenerationJob:
    """
    Job that pre-generates housing reports for the next month.

    This job:
    1. Calculates the target month (next month)
    2. Fetches all countries that have documents
    3. Generates reports for each country sequentially
    4. Logs results and tracks failures
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.auth_client = AuthClient(settings)
        self.agent_client = AgentApiClient(settings, self.auth_client)
        self._last_result: JobResult | None = None
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def last_result(self) -> JobResult | None:
        return self._last_result

    async def run(self, target_month: str | None = None) -> JobResult:
        """
        Execute the report pre-generation job.

        Args:
            target_month: Optional override for target month (YYYY-MM).
                         If not provided, uses next month.
        """
        if self._is_running:
            logger.warning("Job is already running, skipping")
            return JobResult(
                job_name="report_pregeneration",
                started_at=datetime.now(),
                success=False,
                error_message="Job is already running",
            )

        self._is_running = True
        result = JobResult(
            job_name="report_pregeneration",
            started_at=datetime.now(),
        )

        # Determine target month
        month = target_month or get_next_month()
        logger.info(f"Starting report pre-generation job for month: {month}")

        try:
            # 1. Fetch countries with documents
            countries = await self.agent_client.get_countries_with_documents(
                access_scope=self.settings.report_access_scope
            )

            if not countries:
                logger.warning("No countries found with documents")
                result.success = True
                result.completed_at = datetime.now()
                return result

            result.total_items = len(countries)
            logger.info(f"Processing {len(countries)} countries")

            # 2. Generate reports sequentially
            for i, country_code in enumerate(countries, 1):
                logger.info(f"[{i}/{len(countries)}] Generating report for {country_code}...")

                success, status, message = await self.agent_client.generate_report(
                    country_code=country_code,
                    target_month=month,
                    skip_cache=True,  # Always regenerate for pre-generation
                )

                if success:
                    result.succeeded_items += 1
                    logger.info(f"[{i}/{len(countries)}] {country_code}: OK")
                else:
                    result.failed_items += 1
                    result.failed_details.append({
                        "country_code": country_code,
                        "status": status,
                        "message": message,
                    })
                    logger.error(f"[{i}/{len(countries)}] {country_code}: FAILED ({status})")

                # Delay between reports
                if i < len(countries):
                    await asyncio.sleep(self.settings.delay_between_reports_seconds)

            # 3. Determine overall success
            result.success = result.failed_items == 0
            result.completed_at = datetime.now()

            logger.info(
                f"Job completed: {result.succeeded_items}/{result.total_items} succeeded, "
                f"{result.failed_items} failed, duration: {result.duration_seconds:.1f}s"
            )

        except Exception as e:
            logger.exception(f"Job failed with error: {e}")
            result.success = False
            result.error_message = str(e)
            result.completed_at = datetime.now()

        finally:
            self._is_running = False
            self._last_result = result

        return result


__all__ = ["ReportPreGenerationJob", "JobResult", "get_next_month"]

