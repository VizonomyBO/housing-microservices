"""Typer CLI entrypoint for the reduced E2E smoke workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from .runner import SmokeRunConfig, run_smoke

app = typer.Typer(help="Run the reduced-profile end-to-end smoke test via HTTP APIs.")

AUTH_BASE_URL_OPTION = typer.Option(
    "http://localhost:5001",
    envvar="AUTH_SERVICE_URL",
    help="Base URL for the auth-service (e.g., http://localhost:5001)",
)

AGENT_BASE_URL_OPTION = typer.Option(
    "http://localhost:8000",
    envvar="AGENT_API_URL",
    help="Base URL for the Agent API service",
)

DATABASE_URL_OPTION = typer.Option(
    None,
    envvar="DATABASE_URL",
    help="Async SQLAlchemy DATABASE_URL used for conversation bootstrap",
)

LOCALSTACK_URL_OPTION = typer.Option(
    None,
    envvar="AWS_ENDPOINT_URL",
    help="Optional LocalStack endpoint (http://localhost.localstack.cloud:4566)",
)

EMAIL_OPTION = typer.Option(
    "ava.reduced+demo@example.com",
    envvar="REDUCED_E2E_EMAIL",
    help="Demo user email",
)

USERNAME_OPTION = typer.Option(
    "ava_demo",
    envvar="REDUCED_E2E_USERNAME",
    help="Demo username",
)

PASSWORD_OPTION = typer.Option(
    "DemoPassw0rd!",
    envvar="REDUCED_E2E_PASSWORD",
    help="Demo password",
)

FIRST_NAME_OPTION = typer.Option(
    "Ava",
    envvar="REDUCED_E2E_FIRST_NAME",
    help="Demo user first name",
)

LAST_NAME_OPTION = typer.Option(
    "Rivera",
    envvar="REDUCED_E2E_LAST_NAME",
    help="Demo user last name",
)

COUNTRY_OPTION = typer.Option(
    "USA",
    envvar="REDUCED_E2E_COUNTRY",
    help="Country code used for documents + conversation bootstrap",
)

LANGUAGE_OPTION = typer.Option(
    "en",
    envvar="REDUCED_E2E_LANGUAGE",
    help="Language metadata applied to uploads",
)

REPORT_PATH_OPTION = typer.Option(
    Path("logs/reduced_e2e_smoke.json"),
    envvar="REDUCED_E2E_REPORT",
    help="Path to the JSON summary report",
)

STREAM_CAPABILITY_OPTION = typer.Option(
    ["cross_doc_reasoning"],
    help="Prompt capabilities that should run in streaming mode",
)

TIMEOUT_OPTION = typer.Option(30.0, help="HTTP client timeout in seconds")

SKIP_PILLARS_OPTION = typer.Option(False, help="Skip the pillars endpoint validation")


@app.command("run")
def run(
    auth_base_url: str = AUTH_BASE_URL_OPTION,
    agent_base_url: str = AGENT_BASE_URL_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    localstack_url: str | None = LOCALSTACK_URL_OPTION,
    email: str = EMAIL_OPTION,
    username: str = USERNAME_OPTION,
    password: str = PASSWORD_OPTION,
    first_name: str = FIRST_NAME_OPTION,
    last_name: str = LAST_NAME_OPTION,
    country_code: str = COUNTRY_OPTION,
    language: str = LANGUAGE_OPTION,
    report_path: Path = REPORT_PATH_OPTION,
    stream_capability: list[str] = STREAM_CAPABILITY_OPTION,
    timeout_seconds: float = TIMEOUT_OPTION,
    skip_pillars: bool = SKIP_PILLARS_OPTION,
) -> None:
    """Execute the reduced-profile smoke workflow."""

    config = SmokeRunConfig(
        auth_base_url=auth_base_url,
        agent_base_url=agent_base_url,
        report_path=report_path,
        email=email,
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        country_code=country_code,
        language=language,
        tags=("reduced_e2e", "demo"),
        timeout_seconds=timeout_seconds,
        stream_capabilities=set(stream_capability),
        database_url=database_url,
        localstack_url=localstack_url,
        skip_pillars=skip_pillars,
    )
    summary = asyncio.run(run_smoke(config))
    raise typer.Exit(code=0 if summary.success else 1)


__all__ = ["app"]
