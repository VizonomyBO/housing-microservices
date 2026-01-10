"""Job definitions for scheduled tasks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from job_service.clients import AgentApiClient, AuthClient
from job_service.countries import ISO_ALPHA3_CODES
from job_service.settings import Settings

logger = logging.getLogger(__name__)


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
    skipped_items: int = 0
    failed_details: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


class ReportPreGenerationJob:
    """
    Job that regenerates housing reports for all countries.

    This job runs on the 25th of each month and:
    1. Iterates through all ISO-3 country codes
    2. Generates reports with skip_cache=True to force regeneration
    3. Each report overwrites the existing cached version
    4. Reports expire 30 days after generation

    The 25th timing ensures reports are refreshed before they expire
    (assuming initial generation around the 1st of the month).
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

    async def run(self) -> JobResult:
        """
        Execute the report pre-generation job.

        Regenerates all country reports with skip_cache setting from config,
        overwriting the existing cached versions if skip_cache=True.
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

        skip_cache = self.settings.skip_cache
        start_from = self.settings.start_from_country

        logger.info(
            f"Starting report regeneration job "
            f"(skip_cache={skip_cache}, start_from={start_from or 'beginning'})"
        )

        try:
            # Use all ISO-3 country codes - regional/global docs provide content
            # even for countries without direct documents
            countries = list(ISO_ALPHA3_CODES)
            result.total_items = len(countries)

            # Find start index if resuming
            start_index = 0
            if start_from:
                try:
                    start_index = countries.index(start_from)
                    logger.info(f"Resuming from {start_from} (index {start_index})")
                except ValueError:
                    logger.warning(
                        f"Start country '{start_from}' not found in list, starting from beginning"
                    )

            logger.info(
                f"Processing {len(countries) - start_index} of {len(countries)} ISO-3 country codes"
            )

            # Generate reports sequentially
            for i, country_code in enumerate(countries, 1):
                # Skip countries before start_from
                if i - 1 < start_index:
                    result.skipped_items += 1
                    continue

                logger.info(f"[{i}/{len(countries)}] Generating report for {country_code}...")

                success, status, message = await self.agent_client.generate_report(
                    country_code=country_code,
                    skip_cache=skip_cache,
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

            # Determine overall success
            result.success = result.failed_items == 0
            result.completed_at = datetime.now()

            logger.info(
                f"Job completed: {result.succeeded_items}/{result.total_items} succeeded, "
                f"{result.failed_items} failed, {result.skipped_items} skipped, "
                f"duration: {result.duration_seconds:.1f}s"
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


__all__ = ["ReportPreGenerationJob", "JobResult"]
