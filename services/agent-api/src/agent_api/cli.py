"""Typer CLI exposing reduced-scope runtime helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

import typer
from shared_data_layer.db.session import DatabaseSessionManager

from agent_api.settings import Settings, load_settings
from services import (
    PillarService,
    ReducedScopeIngestionJobService,
    ReducedScopeWorkerRuntime,
)
from services.reduced_scope_runtime import IngestionCompletionPayload

app = typer.Typer(help="Synchronous workerless runtime commands")


def _require_database(settings: Settings) -> str:
    if not settings.database_url:
        typer.echo("DATABASE_URL must be configured for CLI commands", err=True)
        raise typer.Exit(code=2)
    return settings.database_url


async def _with_runtime(
    callback: Callable[[Settings, ReducedScopeWorkerRuntime], Awaitable[None]],
) -> None:
    settings = load_settings()
    database_url = _require_database(settings)
    DatabaseSessionManager.init(database_url)
    try:
        async with DatabaseSessionManager.session() as session:
            ingestion_service = ReducedScopeIngestionJobService(
                session,
                allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
            )
            pillar_service = PillarService(
                session,
                allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
            )
            runtime = ReducedScopeWorkerRuntime(
                session=session,
                ingestion_service=ingestion_service,
                pillar_service=pillar_service,
                allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
            )
            await callback(settings, runtime)
            await session.commit()
    finally:
        await DatabaseSessionManager.dispose()


@app.command("run-ingestion")
def run_ingestion(
    document_id: str,
    chunk_type: Annotated[str, typer.Option("--chunk-type", help="Chunk type")] = "text",
) -> None:
    """Finalize a document ingestion job inline."""

    async def _runner(settings: Settings, runtime: ReducedScopeWorkerRuntime) -> None:
        summary = await runtime.complete_ingestion_job(
            document_id=document_id,
            payload=IngestionCompletionPayload(chunk_type=chunk_type),
        )
        typer.echo(f"Completed ingestion job {summary.id} for document {summary.document_id}")

    asyncio.run(_with_runtime(_runner))


@app.command("generate-pillars")
def generate_pillars(
    country_code: Annotated[
        str | None, typer.Option("--country-code", help="Limit generation to this ISO-3 country")
    ] = None,
    conversation_id: Annotated[
        str | None,
        typer.Option("--conversation-id", help="Generate answers for a specific conversation"),
    ] = None,
    pillar: Annotated[
        list[str] | None, typer.Option("--pillar", help="Specify one or more pillar names")
    ] = None,
) -> None:
    """Generate and persist pillar answers synchronously."""

    if not country_code and not conversation_id:
        raise typer.BadParameter("Provide either --country-code or --conversation-id")

    async def _runner(settings: Settings, runtime: ReducedScopeWorkerRuntime) -> None:
        answers = await runtime.generate_pillar_answers(
            country_code=country_code,
            conversation_id=conversation_id,
            pillars=pillar,
        )
        typer.echo(f"Generated {len(answers)} pillar answers")

    asyncio.run(_with_runtime(_runner))


@app.command("generate-artifact")
def generate_artifact(
    conversation_id: Annotated[
        str, typer.Option("--conversation-id", help="Conversation identifier")
    ],
    artifact_type: Annotated[
        str, typer.Option("--artifact-type", help="Artifact type label")
    ] = "chat_export",
) -> None:
    """Insert placeholder artifact metadata without external storage."""

    async def _runner(settings: Settings, runtime: ReducedScopeWorkerRuntime) -> None:
        artifacts = await runtime.generate_artifact(
            conversation_id=conversation_id,
            artifact_type=artifact_type,
        )
        typer.echo(
            f"Recorded {len(artifacts)} artifact placeholder(s) for conversation {conversation_id}"
        )

    asyncio.run(_with_runtime(_runner))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    app()
