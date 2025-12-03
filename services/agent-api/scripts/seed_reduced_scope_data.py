#!/usr/bin/env python3
"""Populate markitdown-style demo data for reduced-scope runs."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from shared_data_layer.db.models.conversations import Conversation, Message
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.retrieval import Chunk
from shared_data_layer.db.session import DatabaseSessionManager
from shared_data_layer.repositories.documents import DocumentRepository
from sqlalchemy import select

from repositories.conversation_scope_repository import ConversationScopeRepository
from services.ingestion_job_service import ReducedScopeIngestionJobService
from services.pillar_service import PillarService
from services.reduced_scope_runtime import (
    IngestionCompletionPayload,
    ReducedScopeWorkerRuntime,
)

DEMO_OWNER_ID = uuid5(NAMESPACE_URL, "agent-api-demo-owner")


@dataclass(frozen=True)
class DemoDocument:
    canonical_name: str
    country_code: str
    language: str
    content: str
    source_uri: str
    tags: tuple[str, ...]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


DEMO_DOCUMENTS = (
    DemoDocument(
        canonical_name="Housing Stability Pillar Overview",
        country_code="USA",
        language="en",
        content="""
        ## Housing Stability Update 2024
        - Rental assistance expanded across three pilot cities.
        - Pillar metrics improved after community land trust adoption.
        - Markitdown ingestion feeds text-only context for LangGraph demos.
        """.strip(),
        source_uri="https://example.com/demo/housing-stability",
        tags=("demo", "markitdown", "housing"),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed reduced-scope demo data.")
    parser.add_argument(
        "--database-url",
        dest="database_url",
        help="Override DATABASE_URL env var",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-seed even if demo chunks already exist",
    )
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="Skip seeding when chunks are already present",
    )
    return parser.parse_args()


def require_database_url(cli_value: str | None) -> str:
    url = cli_value or os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL must be set via env or --database-url")
    return url


async def has_existing_chunks(session) -> bool:
    result = await session.execute(select(Chunk.id).limit(1))
    return result.scalar_one_or_none() is not None


async def ensure_demo_document(session, spec: DemoDocument) -> Document:
    repo = DocumentRepository(session)
    document = await repo.create_or_get_document(
        owner_user_id=None,
        content_hash=spec.content_hash,
        access_scope="base",
        canonical_name=spec.canonical_name,
        country_code=spec.country_code,
        language=spec.language,
        status="ingesting",
        ingestion_stage="chunk",
        managed_by="reduced_scope_demo",
        tags=list(spec.tags),
        metadata_={
            "auto_attach_enabled": True,
            "source": "markitdown_demo",
        },
    )
    document.source_uri = spec.source_uri
    document.byte_size = len(spec.content.encode("utf-8"))
    await session.flush()
    return document


async def ensure_chunk(session, document: Document, text: str) -> Chunk:
    digest = hashlib.sha256(f"{document.id}:{text}".encode()).hexdigest()
    stmt = select(Chunk).where(Chunk.document_id == document.id, Chunk.content_hash == digest)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing
    chunk = Chunk(
        document_id=document.id,
        position=0,
        chunk_type="text",
        page_number=1,
        text_content=text,
        content_hash=digest,
        country_code=document.country_code or "USA",
        metadata_={"ingestion": "markitdown_demo"},
    )
    session.add(chunk)
    await session.flush()
    return chunk


async def ensure_conversation(session, *, country_code: str) -> Conversation:
    conv_id = uuid5(NAMESPACE_URL, f"agent-api-demo-conv-{country_code}")
    conversation = await session.get(Conversation, conv_id)
    if conversation:
        return conversation
    conversation = Conversation(
        id=conv_id,
        owner_user_id=DEMO_OWNER_ID,
        country_code=country_code,
        status="active",
        title=f"Demo Conversation ({country_code})",
        metadata_={"created_by": "seed_reduced_scope_data"},
    )
    session.add(conversation)
    await session.flush()
    await ensure_demo_messages(session, conversation)
    return conversation


async def ensure_demo_messages(session, conversation: Conversation) -> None:
    stmt = select(Message).where(Message.conversation_id == conversation.id)
    existing = (await session.execute(stmt)).scalars().first()
    if existing:
        return
    now = datetime.now(UTC)
    session.add_all(
        [
            Message(
                conversation_id=conversation.id,
                role="user",
                ordinal=0,
                content={
                    "text": "How stable is the housing program this quarter?",
                    "created_at": now.isoformat(),
                },
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                ordinal=1,
                content={
                    "text": "Reviewing base documents for housing stability.",
                    "created_at": now.isoformat(),
                },
            ),
        ]
    )


async def attach_document(
    session,
    conversation: Conversation,
    document: Document,
) -> None:
    scope_repo = ConversationScopeRepository(session)
    await scope_repo.ensure_attachment(
        conversation_id=conversation.id,
        document_id=document.id,
        attach_source="seed_script",
        role="primary",
        visibility_override="visible",
        attached_by_user_id=DEMO_OWNER_ID,
    )


async def seed_demo_data(args: argparse.Namespace) -> None:
    db_url = require_database_url(args.database_url)
    DatabaseSessionManager.init(db_url)
    try:
        async with DatabaseSessionManager.session() as session:
            if args.if_empty and not args.force and await has_existing_chunks(session):
                print("Chunks already present; skipping seed due to --if-empty")
                return

            seeded = 0
            conversation: Conversation | None = None
            ingestion_service = ReducedScopeIngestionJobService(session)
            pillar_service = PillarService(session)
            runtime = ReducedScopeWorkerRuntime(
                session=session,
                ingestion_service=ingestion_service,
                pillar_service=pillar_service,
                allowed_chunk_types=("text",),
            )

            for spec in DEMO_DOCUMENTS:
                document = await ensure_demo_document(session, spec)
                await ensure_chunk(session, document, spec.content)
                conversation = await ensure_conversation(session, country_code=spec.country_code)
                await attach_document(session, conversation, document)
                await runtime.complete_ingestion_job(
                    document_id=document.id,
                    payload=IngestionCompletionPayload(
                        metadata={"seeded_at": datetime.now(UTC).isoformat()}
                    ),
                )
                await runtime.generate_pillar_answers(country_code=spec.country_code)
                seeded += 1

            await session.commit()
            print(f"Seeded {seeded} base document(s) into {db_url}")
    finally:
        await DatabaseSessionManager.dispose()


def main() -> None:
    args = parse_args()
    asyncio.run(seed_demo_data(args))


if __name__ == "__main__":
    main()
