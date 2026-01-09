"""Configuration settings for the job service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class ScheduleConfig:
    """Configuration for report pre-generation schedule."""

    # Day of month to run pre-generation (1-28)
    day_of_month: int = 25
    # Hour to run (0-23)
    hour: int = 2
    # Minute to run (0-59)
    minute: int = 0
    # Whether to run job on startup (useful for testing)
    run_on_startup: bool = False


@dataclass(slots=True)
class AgentApiConfig:
    """Configuration for Agent API client."""

    base_url: str = "http://localhost:8000"
    timeout_seconds: float = 600.0  # 10 minutes per report


@dataclass(slots=True)
class AuthConfig:
    """Configuration for authentication."""

    base_url: str = "http://localhost:5001"
    # Service account credentials for job execution
    email: str = ""
    password: str = ""


@dataclass(slots=True)
class Settings:
    """Application settings."""

    service_name: str = "job-service"
    http_port: int = 8090
    log_level: str = "INFO"

    # Scheduling
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    # API clients
    agent_api: AgentApiConfig = field(default_factory=AgentApiConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    # Job configuration
    report_access_scope: str = "base"  # Filter documents by this scope
    max_concurrent_reports: int = 1  # Sequential by default
    delay_between_reports_seconds: int = 5


def load_settings() -> Settings:
    """Load settings from environment variables."""
    schedule = ScheduleConfig(
        day_of_month=int(os.getenv("JOB_SCHEDULE_DAY", "25")),
        hour=int(os.getenv("JOB_SCHEDULE_HOUR", "2")),
        minute=int(os.getenv("JOB_SCHEDULE_MINUTE", "0")),
        run_on_startup=os.getenv("JOB_RUN_ON_STARTUP", "").lower() in ("1", "true", "yes"),
    )

    agent_api = AgentApiConfig(
        base_url=os.getenv("AGENT_BASE_URL", "http://agent-api:8000"),
        timeout_seconds=float(os.getenv("JOB_REPORT_TIMEOUT_SECONDS", "600")),
    )

    auth = AuthConfig(
        base_url=os.getenv("AUTH_BASE_URL", "http://auth-service:5001"),
        email=os.getenv("JOB_SERVICE_EMAIL", os.getenv("PROD_DEMO_EMAIL", "")),
        password=os.getenv("JOB_SERVICE_PASSWORD", os.getenv("PROD_DEMO_PASSWORD", "")),
    )

    return Settings(
        service_name=os.getenv("SERVICE_NAME", "job-service"),
        http_port=int(os.getenv("JOB_SERVICE_PORT", "8090")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        schedule=schedule,
        agent_api=agent_api,
        auth=auth,
        report_access_scope=os.getenv("JOB_REPORT_ACCESS_SCOPE", "base"),
        max_concurrent_reports=int(os.getenv("JOB_MAX_CONCURRENT_REPORTS", "1")),
        delay_between_reports_seconds=int(os.getenv("JOB_DELAY_BETWEEN_REPORTS", "5")),
    )


__all__ = ["Settings", "load_settings"]

