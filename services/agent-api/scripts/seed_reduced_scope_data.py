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
        - Rental assistance expanded across three pilot cities: Arroyo Vista, Brookhaven, and District 9.
        - Pillar metrics improved 14% after community land trust adoption; District 9's land trust now owns 210 units.
        - Text-only context is optimized for LangGraph demos so analysts can trace every recommendation back to the memo.
        """.strip(),
        source_uri="https://example.com/demo/housing-stability",
        tags=("demo", "markitdown", "housing"),
    ),
    DemoDocument(
        canonical_name="Voucher Expansion Guardrails FY24",
        country_code="USA",
        language="en",
        content="""
        ### Voucher Expansion Guardrails
        1. **Equity Cap:** No more than 65% of a borough's total vouchers may be allocated to a single developer; excess vouchers must be rebalanced within 30 days.
        2. **Affordability Floor:** Any building that receives expansion vouchers must prove tenants spend **< 35%** of income on rent after subsidies; automatic clawbacks trigger if the ratio exceeds 40% for two consecutive months.

        The memo also directs housing teams to pair the guardrails with District 9's community land trust so voucher families can graduate into permanently affordable units once their arrears fall below $500.
        """.strip(),
        source_uri="https://example.com/demo/voucher-guardrails",
        tags=("demo", "policy", "voucher"),
    ),
    DemoDocument(
        canonical_name="District 9 Relief Ledger",
        country_code="USA",
        language="en",
        content="""
        ## District 9 Ledger Insights (Nov 2024)
        - 118 renter households carry **>$1,200** in arrears; 46% of them live in the CLT pipeline waiting for rehab.
        - Utility delinquencies jumped 19% after energy prices spiked; seniors cite unpredictable payment plans.
        - Cash flow review shows the hardship fund can cover **$250k** in one-time arrears credits if disbursed in two waves.

        ### Suggested Plays
        - Pair guardrail-compliant vouchers with the arrears credits so families can requalify within 45 days.
        - Launch an **energy-coaching plus direct-pay** pilot so the city pays the utility first and back-bills renters only for verified usage.
        """.strip(),
        source_uri="https://example.com/demo/d9-ledger",
        tags=("demo", "ledger", "district9"),
    ),
    DemoDocument(
        canonical_name="District 9 KPI Dashboard",
        country_code="USA",
        language="en",
        content="""
        ### KPI Table (Nov 2024)

        | City / Zone     | KPI                     | Value |
        |-----------------|------------------------|-------|
        | Arroyo Vista    | Housing Stability Score | 78    |
        | Brookhaven      | Housing Stability Score | 82    |
        | District 9 Core | Housing Stability Score | 88    |
        | District 9 East | Voucher Utilization %  | 91    |

        Any KPI exceeding **80** triggers a proactive coaching action plan, while values below 80 require remediation memos.
        """.strip(),
        source_uri="https://example.com/demo/d9-kpis",
        tags=("demo", "kpi", "table"),
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
