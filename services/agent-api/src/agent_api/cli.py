"""Typer CLI exposing reduced-scope runtime helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

import typer
from shared_data_layer.db.maintenance import (
    refresh_active_chunks_view,
    refresh_base_documents_cache_for_country,
)
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.retrieval import Chunk
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.settings import Settings, load_settings
from services import (
    PillarService,
    ReducedScopeIngestionJobService,
    ReducedScopeWorkerRuntime,
)
from services.model_clients import VoyageEmbeddingClient
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
    if not settings.reduced_scope.is_enabled():
        typer.echo(
            "Reduced scope runtime is disabled. Enable REDUCED_SCOPE_ENABLED=1 only for "
            "demo/testing or use the production ingestion/export pipeline.",
            err=True,
        )
        raise typer.Exit(code=2)
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


async def _with_session(
    callback: Callable[[Settings, AsyncSession], Awaitable[None]],
) -> None:
    settings = load_settings()
    database_url = _require_database(settings)
    DatabaseSessionManager.init(database_url)
    try:
        async with DatabaseSessionManager.session() as session:
            await callback(settings, session)
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


@app.command("reembed-chunks")
def reembed_chunks(
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            "-l",
            help="Maximum number of chunks to re-embed (defaults to all)",
        ),
    ] = None,
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size",
            "-b",
            help="Chunk batch size for embedding calls",
        ),
    ] = 64,
    document_id: Annotated[
        list[str] | None,
        typer.Option(
            "--document-id",
            "-d",
            help="Restrict re-embedding to specific document IDs (repeatable)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Count eligible chunks without writing embeddings"),
    ] = False,
) -> None:
    """Re-embed existing chunks using the configured Voyage embedding model."""

    async def _runner(settings: Settings, session) -> None:  # noqa: PLR0912
        if not settings.voyage_api_key:
            typer.echo("VOYAGE_API_KEY is required to re-embed chunks", err=True)
            raise typer.Exit(code=2)

        voyage_client = VoyageEmbeddingClient(
            api_key=settings.voyage_api_key,
            model=settings.voyage_embedding_model,
        )
        doc_filters: list[UUID] | None = None
        if document_id:
            doc_filters = []
            for raw in document_id:
                try:
                    doc_filters.append(UUID(raw))
                except ValueError as exc:
                    raise typer.BadParameter(f"Invalid document_id: {raw}") from exc

        processed = 0
        base_countries: set[str] = set()
        last_created_at = None
        last_chunk_id: UUID | None = None

        while True:
            remaining = limit - processed if limit is not None else batch_size
            batch_limit = batch_size if limit is None else max(0, min(batch_size, remaining))
            if batch_limit == 0:
                break

            stmt = (
                select(
                    Chunk,
                    Document.access_scope,
                    Document.country_code.label("document_country"),
                )
                .join(Document, Document.id == Chunk.document_id)
                .where(Chunk.chunk_type == "text")
                .where(Chunk.text_content.is_not(None))
                .order_by(Chunk.created_at, Chunk.id)
                .limit(batch_limit)
            )
            if doc_filters:
                stmt = stmt.where(Chunk.document_id.in_(doc_filters))
            if last_created_at is not None and last_chunk_id is not None:
                stmt = stmt.where(
                    (Chunk.created_at > last_created_at)
                    | ((Chunk.created_at == last_created_at) & (Chunk.id > last_chunk_id))
                )

            rows = (await session.execute(stmt)).all()
            if not rows:
                break

            chunk_batch: list[Chunk] = []
            texts: list[str] = []
            for row in rows:
                chunk: Chunk = row.Chunk
                chunk_batch.append(chunk)
                texts.append(chunk.text_content or "")
                if row.access_scope == "base" and row.document_country:
                    base_countries.add(row.document_country)

            last_created_at = chunk_batch[-1].created_at
            last_chunk_id = chunk_batch[-1].id
            processed += len(chunk_batch)

            if dry_run:
                continue

            embeddings = await voyage_client.embed(texts)
            for chunk, embedding in zip(chunk_batch, embeddings, strict=False):
                chunk.embedding = embedding

            await session.commit()
            typer.echo(
                f"Re-embedded {len(chunk_batch)} chunks "
                f"(total {processed}{'/' + str(limit) if limit else ''})"
            )

        if dry_run:
            typer.echo(f"{processed} chunks eligible for re-embedding")
            return

        await refresh_active_chunks_view(session)
        for country in sorted(base_countries):
            await refresh_base_documents_cache_for_country(session, country)
        await session.commit()
        typer.echo(
            f"Completed re-embedding {processed} chunks "
            f"with model {settings.voyage_embedding_model}"
        )

    asyncio.run(_with_session(_runner))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    app()
