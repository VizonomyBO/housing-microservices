"""initial schema

Revision ID: 000000000001
Revises:
Create Date: 2025-11-26 18:30:00.000000

This migration establishes the full shared data layer schema as described
in DATA_LAYER_GAP_PLAN.md. It creates all base tables, views, triggers,
and stored procedures required by the documents, conversations,
retrieval, knowledge graph, and workflow domains.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from shared_data_layer.db.ltree import LtreeType

revision: str = "000000000001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ISO 3166-1 alpha-3 codes sourced from
# https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.json
ISO_ALPHA3_CODES: tuple[str, ...] = (
    "ABW",
    "AFG",
    "AGO",
    "AIA",
    "ALA",
    "ALB",
    "AND",
    "ARE",
    "ARG",
    "ARM",
    "ASM",
    "ATA",
    "ATF",
    "ATG",
    "AUS",
    "AUT",
    "AZE",
    "BDI",
    "BEL",
    "BEN",
    "BES",
    "BFA",
    "BGD",
    "BGR",
    "BHR",
    "BHS",
    "BIH",
    "BLM",
    "BLR",
    "BLZ",
    "BMU",
    "BOL",
    "BRA",
    "BRB",
    "BRN",
    "BTN",
    "BVT",
    "BWA",
    "CAF",
    "CAN",
    "CCK",
    "CHE",
    "CHL",
    "CHN",
    "CIV",
    "CMR",
    "COD",
    "COG",
    "COK",
    "COL",
    "COM",
    "CPV",
    "CRI",
    "CUB",
    "CUW",
    "CXR",
    "CYM",
    "CYP",
    "CZE",
    "DEU",
    "DJI",
    "DMA",
    "DNK",
    "DOM",
    "DZA",
    "ECU",
    "EGY",
    "ERI",
    "ESH",
    "ESP",
    "EST",
    "ETH",
    "FIN",
    "FJI",
    "FLK",
    "FRA",
    "FRO",
    "FSM",
    "GAB",
    "GBR",
    "GEO",
    "GGY",
    "GHA",
    "GIB",
    "GIN",
    "GLP",
    "GMB",
    "GNB",
    "GNQ",
    "GRC",
    "GRD",
    "GRL",
    "GTM",
    "GUF",
    "GUM",
    "GUY",
    "HKG",
    "HMD",
    "HND",
    "HRV",
    "HTI",
    "HUN",
    "IDN",
    "IMN",
    "IND",
    "IOT",
    "IRL",
    "IRN",
    "IRQ",
    "ISL",
    "ISR",
    "ITA",
    "JAM",
    "JEY",
    "JOR",
    "JPN",
    "KAZ",
    "KEN",
    "KGZ",
    "KHM",
    "KIR",
    "KNA",
    "KOR",
    "KWT",
    "LAO",
    "LBN",
    "LBR",
    "LBY",
    "LCA",
    "LIE",
    "LKA",
    "LSO",
    "LTU",
    "LUX",
    "LVA",
    "MAC",
    "MAF",
    "MAR",
    "MCO",
    "MDA",
    "MDG",
    "MDV",
    "MEX",
    "MHL",
    "MKD",
    "MLI",
    "MLT",
    "MMR",
    "MNE",
    "MNG",
    "MNP",
    "MOZ",
    "MRT",
    "MSR",
    "MTQ",
    "MUS",
    "MWI",
    "MYS",
    "MYT",
    "NAM",
    "NCL",
    "NER",
    "NFK",
    "NGA",
    "NIC",
    "NIU",
    "NLD",
    "NOR",
    "NPL",
    "NRU",
    "NZL",
    "OMN",
    "PAK",
    "PAN",
    "PCN",
    "PER",
    "PHL",
    "PLW",
    "PNG",
    "POL",
    "PRI",
    "PRK",
    "PRT",
    "PRY",
    "PSE",
    "PYF",
    "QAT",
    "REU",
    "ROU",
    "RUS",
    "RWA",
    "SAU",
    "SDN",
    "SEN",
    "SGP",
    "SGS",
    "SHN",
    "SJM",
    "SLB",
    "SLE",
    "SLV",
    "SMR",
    "SOM",
    "SPM",
    "SRB",
    "SSD",
    "STP",
    "SUR",
    "SVK",
    "SVN",
    "SWE",
    "SWZ",
    "SXM",
    "SYC",
    "SYR",
    "TCA",
    "TCD",
    "TGO",
    "THA",
    "TJK",
    "TKL",
    "TKM",
    "TLS",
    "TON",
    "TTO",
    "TUN",
    "TUR",
    "TUV",
    "TWN",
    "TZA",
    "UGA",
    "UKR",
    "UMI",
    "URY",
    "USA",
    "UZB",
    "VAT",
    "VCT",
    "VEN",
    "VGB",
    "VIR",
    "VNM",
    "VUT",
    "WLF",
    "WSM",
    "YEM",
    "ZAF",
    "ZMB",
    "ZWE",
)


def create_chunk_partitions() -> None:
    partition_map = {
        "usa": ["USA"],
        "gbr": ["GBR"],
        "can": ["CAN"],
    }
    for suffix, values in partition_map.items():
        formatted_values = ", ".join(f"'{value}'" for value in values)
        op.execute(
            f"""
            CREATE TABLE IF NOT EXISTS chunks_{suffix}
            PARTITION OF chunks
            FOR VALUES IN ({formatted_values})
            """
        )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks_default
        PARTITION OF chunks
        DEFAULT
        """
    )


def create_documents_domain() -> None:
    op.create_table(
        "documents",
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("access_scope", sa.String(), nullable=False),
        sa.Column("canonical_name", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("ingestion_stage", sa.String(), nullable=True),
        sa.Column("ingestion_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingestion_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("source_uri", sa.String(), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=True),
        sa.Column("managed_by", sa.String(), nullable=True),
        sa.Column(
            "active_chat_refs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "access_scope <> 'base' OR owner_user_id IS NULL",
            name="ck_documents_base_owner_null",
        ),
        sa.CheckConstraint(
            "access_scope <> 'base' OR country_code IS NOT NULL",
            name="ck_documents_base_country_required",
        ),
        sa.CheckConstraint(
            "(access_scope = 'base' AND owner_user_id IS NULL)"
            " OR (access_scope <> 'base' AND owner_user_id IS NOT NULL)",
            name="ck_documents_owner_required_for_non_base",
        ),
        sa.CheckConstraint(
            "country_code IS NULL OR country_code ~ '^[A-Z]{3}$'",
            name="ck_documents_country_code_format",
        ),
        sa.CheckConstraint(
            "status IN ('registered','ingesting','active','failed','archived')",
            name="ck_documents_status_enum",
        ),
        sa.CheckConstraint(
            "access_scope IN ('base','user_private','user_shared')",
            name="ck_documents_access_scope_enum",
        ),
        sa.CheckConstraint(
            "ingestion_stage IS NULL OR ingestion_stage IN "
            "('preflight','convert','chunk','embed','index','activate')",
            name="ck_documents_ingestion_stage_enum",
        ),
        sa.CheckConstraint(
            "active_chat_refs >= 0", name="ck_documents_active_refs_non_negative"
        ),
    )

    op.create_index(
        "ix_documents_status_updated_at",
        "documents",
        ["status", "updated_at"],
    )
    op.create_index(
        "ix_documents_scope_country",
        "documents",
        ["access_scope", "country_code"],
    )
    op.create_index(
        "uq_documents_owner_content_hash_active",
        "documents",
        ["owner_user_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_documents_base_country_hash",
        "documents",
        ["country_code", "content_hash"],
        unique=True,
        postgresql_where=sa.text(
            "owner_user_id IS NULL AND access_scope = 'base' AND deleted_at IS NULL"
        ),
    )
    op.create_index(
        "uq_documents_owner_canonical_name_active",
        "documents",
        [sa.text("owner_user_id"), sa.text("lower(canonical_name)")],
        unique=True,
        postgresql_where=sa.text(
            "owner_user_id IS NOT NULL AND access_scope <> 'base' AND deleted_at IS NULL"
        ),
    )

    op.create_table(
        "document_gc_events",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("prev_active_chat_refs", sa.Integer(), nullable=True),
        sa.Column("new_active_chat_refs", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_document_gc_events_document",
        ),
    )
    op.create_index(
        "ix_document_gc_events_document",
        "document_gc_events",
        ["document_id", "created_at"],
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("worker", sa.String(), nullable=True),
        sa.Column("last_error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_ingestion_jobs_document",
        ),
        sa.CheckConstraint(
            "stage IN ('preflight','convert','chunk','embed','index','activate')",
            name="ck_ingestion_jobs_stage_enum",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','canceled')",
            name="ck_ingestion_jobs_status_enum",
        ),
    )
    op.create_index(
        "ix_ingestion_jobs_document_stage",
        "ingestion_jobs",
        ["document_id", "stage"],
    )
    op.create_index(
        "ix_ingestion_jobs_status_filter",
        "ingestion_jobs",
        ["status"],
        postgresql_where=sa.text("status IN ('pending','failed')"),
    )

    op.create_table(
        "artifacts",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("s3_uri", sa.String(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("page_range", postgresql.INT4RANGE(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_artifacts_document",
        ),
        sa.UniqueConstraint(
            "document_id", "artifact_type", name="uq_artifacts_document_type"
        ),
    )
    op.create_index(
        "ix_artifacts_metadata_gin",
        "artifacts",
        ["metadata"],
        postgresql_using="gin",
    )


def create_conversations_domain() -> None:
    op.create_table(
        "conversations",
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column(
            "status", sa.String(), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column(
            "document_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active','archived','deleted')",
            name="ck_conversations_status_enum",
        ),
    )

    op.create_table(
        "conversation_documents",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("attached_by_user_id", sa.UUID(), nullable=True),
        sa.Column("attach_source", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("visibility_override", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
            name="fk_conversation_documents_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_conversation_documents_document",
        ),
        sa.PrimaryKeyConstraint(
            "conversation_id", "document_id", name="pk_conversation_documents"
        ),
    )
    op.create_index(
        "ix_conversation_documents_document_id",
        "conversation_documents",
        ["document_id"],
    )
    op.create_index(
        "ix_conversation_documents_attach_source",
        "conversation_documents",
        ["attach_source"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_conversation_documents_soft_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.deleted_at IS NULL THEN
                UPDATE conversation_documents
                SET deleted_at = now(), updated_at = now()
                WHERE conversation_id = OLD.conversation_id
                  AND document_id = OLD.document_id;
                RETURN NULL;
            END IF;

            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_conversation_documents_soft_delete
        BEFORE DELETE ON conversation_documents
        FOR EACH ROW EXECUTE FUNCTION fn_conversation_documents_soft_delete()
        """
    )

    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(), nullable=False, server_default=sa.text("'final'")
        ),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
            name="fk_messages_conversation",
        ),
        sa.CheckConstraint(
            "role IN ('system','user','assistant','tool')",
            name="ck_messages_role_enum",
        ),
    )
    op.create_index(
        "ix_messages_conversation_ordinal",
        "messages",
        ["conversation_id", "ordinal"],
    )

    op.create_table(
        "message_tool_calls",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column(
            "call_index", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status", sa.String(), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            ondelete="CASCADE",
            name="fk_message_tool_calls_message",
        ),
        sa.UniqueConstraint(
            "message_id",
            "tool_name",
            "call_index",
            name="uq_message_tool_calls_unique_invocation",
        ),
    )
    op.create_index(
        "ix_message_tool_calls_message",
        "message_tool_calls",
        ["message_id"],
    )

    op.create_table(
        "message_citations",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("chunk_country_code", sa.String(length=3), nullable=False),
        sa.Column("snippet", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            ondelete="CASCADE",
            name="fk_message_citations_message",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="RESTRICT",
            name="fk_message_citations_chunk",
        ),
    )
    op.create_index(
        "ix_message_citations_chunk",
        "message_citations",
        ["chunk_id"],
    )

    op.create_table(
        "agent_state_checkpoints",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("checkpoint_type", sa.String(), nullable=False),
        sa.Column(
            "step_index", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
            name="fk_agent_state_checkpoints_conversation",
        ),
    )


def create_retrieval_domain() -> None:
    op.create_table(
        "chunks",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column(
            "position", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "chunk_type", sa.String(), nullable=False, server_default=sa.text("'text'")
        ),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("image_caption", sa.Text(), nullable=True),
        sa.Column("schema_summary", sa.Text(), nullable=True),
        sa.Column(
            "table_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("section_path", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(dim=1024), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "country_code",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'UNK'"),
        ),
        sa.Column("artifact_uri", sa.String(), nullable=True),
        sa.Column(
            "text_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(text_content, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_chunks_document",
        ),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count <= 800",
            name="ck_chunks_token_limit",
        ),
        sa.PrimaryKeyConstraint("id", "country_code", name="pk_chunks"),
        postgresql_partition_by="LIST (country_code)",
    )
    create_chunk_partitions()
    op.create_index(
        "ix_chunks_document_position",
        "chunks",
        ["document_id", "chunk_type", "position"],
    )
    op.create_index(
        "ix_chunks_text_tsv_gin",
        "chunks",
        ["text_tsv"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_chunks_country_chunk_type",
        "chunks",
        ["country_code", "chunk_type"],
    )
    op.create_index(
        "ix_chunks_created_at_brin",
        "chunks",
        ["created_at"],
        postgresql_using="brin",
    )
    op.create_index(
        "ix_chunks_updated_at_brin",
        "chunks",
        ["updated_at"],
        postgresql_using="brin",
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_ivfflat
        ON chunks
        USING ivfflat (embedding vector_ip_ops)
        WITH (lists = 100)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
        ON chunks
        USING hnsw (embedding vector_ip_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    op.create_table(
        "chunk_metrics",
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("chunk_country_code", sa.String(length=3), nullable=False),
        sa.Column("quality_score", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "retrieval_count",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="CASCADE",
            name="fk_chunk_metrics_chunk",
        ),
        sa.UniqueConstraint(
            "chunk_id", "chunk_country_code", name="uq_chunk_metrics_chunk"
        ),
    )
    op.create_index(
        "ix_chunk_metrics_chunk_id",
        "chunk_metrics",
        ["chunk_id", "chunk_country_code"],
    )

    op.create_table(
        "retrieval_runs",
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "document_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_retrieval_runs_created_at",
        "retrieval_runs",
        ["created_at"],
    )
    op.create_index(
        "ix_retrieval_runs_document_scope_gin",
        "retrieval_runs",
        ["document_scope"],
        postgresql_using="gin",
    )

    op.create_table(
        "retrieval_run_items",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("chunk_country_code", sa.String(length=3), nullable=False),
        sa.Column("score", sa.Numeric(6, 5), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["retrieval_runs.id"],
            ondelete="CASCADE",
            name="fk_retrieval_run_items_run",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="CASCADE",
            name="fk_retrieval_run_items_chunk",
        ),
    )

    op.create_table(
        "pillar_answers",
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("pillar_name", sa.String(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("score", sa.Numeric(4, 3), nullable=True),
        sa.Column("summary_markdown", sa.Text(), nullable=False),
        sa.Column(
            "answer_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_pillar_answers_document",
        ),
        sa.CheckConstraint(
            "status IN ('draft','running','published','superseded','rejected')",
            name="ck_pillar_answers_status_enum",
        ),
    )
    op.create_index(
        "uq_pillar_answers_owner_country_pillar",
        "pillar_answers",
        ["owner_user_id", "country_code", "pillar_name"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index(
        "ix_pillar_answers_country_pillar",
        "pillar_answers",
        ["country_code", "pillar_name"],
        postgresql_where=sa.text("status = 'published'"),
    )

    op.create_table(
        "pillar_answer_sources",
        sa.Column("pillar_answer_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("chunk_country_code", sa.String(length=3), nullable=False),
        sa.Column("contribution_type", sa.String(), nullable=False),
        sa.Column(
            "weight", sa.Numeric(4, 3), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pillar_answer_id"],
            ["pillar_answers.id"],
            ondelete="CASCADE",
            name="fk_pillar_answer_sources_answer",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="CASCADE",
            name="fk_pillar_answer_sources_chunk",
        ),
        sa.UniqueConstraint(
            "pillar_answer_id",
            "chunk_id",
            "chunk_country_code",
            name="uq_pillar_answer_sources_pair",
        ),
    )


def create_knowledge_graph_domain() -> None:
    op.create_table(
        "graph_entities",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_key", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(dim=512), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("chunk_country_code", sa.String(length=3), nullable=True),
        sa.Column("algo_version", sa.String(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("labels", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Numeric(4, 3), nullable=True),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="SET NULL",
            name="fk_graph_entities_document",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="SET NULL",
            name="fk_graph_entities_chunk",
        ),
        sa.CheckConstraint(
            "(owner_user_id IS NOT NULL) OR country_code IS NOT NULL",
            name="ck_graph_entities_country_or_owner",
        ),
        sa.CheckConstraint(
            "country_code IS NULL OR country_code ~ '^[A-Z]{3}$'",
            name="ck_graph_entities_country_code_format",
        ),
        sa.CheckConstraint(
            "(chunk_id IS NULL AND chunk_country_code IS NULL)"
            " OR (chunk_id IS NOT NULL AND chunk_country_code IS NOT NULL)",
            name="ck_graph_entities_chunk_country_pair",
        ),
    )
    op.create_index("ix_graph_entities_name", "graph_entities", ["name"])
    op.create_index(
        "ix_graph_entities_document_id",
        "graph_entities",
        ["document_id"],
    )
    op.create_index(
        "ix_graph_entities_labels_gin",
        "graph_entities",
        ["labels"],
        postgresql_using="gin",
    )
    op.create_index(
        "uq_graph_entities_base_scope",
        "graph_entities",
        ["entity_type", "entity_key", "country_code"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NULL"),
    )
    op.create_index(
        "uq_graph_entities_user_scope",
        "graph_entities",
        ["entity_type", "entity_key", "owner_user_id"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NOT NULL"),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_graph_entities_embedding_hnsw
        ON graph_entities
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 8, ef_construction = 64)
        """
    )
    op.create_table(
        "graph_edges",
        sa.Column("source_entity_id", sa.UUID(), nullable=False),
        sa.Column("target_entity_id", sa.UUID(), nullable=False),
        sa.Column("edge_type", sa.String(), nullable=False),
        sa.Column(
            "weight", sa.Numeric(4, 3), nullable=True, server_default=sa.text("1")
        ),
        sa.Column(
            "directional", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("evidence_span", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("algo_version", sa.String(), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_entity_id"],
            ["graph_entities.id"],
            ondelete="CASCADE",
            name="fk_graph_edges_source",
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"],
            ["graph_entities.id"],
            ondelete="CASCADE",
            name="fk_graph_edges_target",
        ),
        sa.UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "edge_type",
            name="uq_graph_edges_source_target_type",
        ),
    )
    op.create_index(
        "ix_graph_edges_source_type",
        "graph_edges",
        ["source_entity_id", "edge_type"],
    )
    op.create_index(
        "ix_graph_edges_target_type",
        "graph_edges",
        ["target_entity_id", "edge_type"],
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_graph_edges_seen_brin
        ON graph_edges
        USING brin (first_seen_at, last_seen_at)
        """
    )
    op.create_table(
        "graph_evidence",
        sa.Column("edge_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("chunk_country_code", sa.String(length=3), nullable=True),
        sa.Column("offsets", postgresql.INT4RANGE(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["edge_id"],
            ["graph_edges.id"],
            ondelete="CASCADE",
            name="fk_graph_evidence_edge",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="SET NULL",
            name="fk_graph_evidence_chunk",
        ),
        sa.CheckConstraint(
            "(chunk_id IS NULL AND chunk_country_code IS NULL)"
            " OR (chunk_id IS NOT NULL AND chunk_country_code IS NOT NULL)",
            name="ck_graph_evidence_chunk_pair",
        ),
    )

    op.create_table(
        "graph_communities",
        sa.Column("community_key", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("entity_ids", postgresql.ARRAY(postgresql.UUID()), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column("algo_version", sa.String(), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "community_key", "algo_version", name="uq_graph_communities_key_algo"
        ),
    )
    op.create_index(
        "ix_graph_communities_country_level",
        "graph_communities",
        ["country_code", "level"],
    )
    op.create_index(
        "ix_graph_communities_entity_ids_gin",
        "graph_communities",
        ["entity_ids"],
        postgresql_using="gin",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION graph_communities_normalize()
        RETURNS TRIGGER AS $$
        DECLARE
            cleaned uuid[];
        BEGIN
            IF NEW.entity_ids IS NOT NULL THEN
                SELECT ARRAY(
                    SELECT DISTINCT e FROM unnest(NEW.entity_ids) e ORDER BY e
                ) INTO cleaned;
                NEW.entity_ids := cleaned;
                NEW.metrics := coalesce(NEW.metrics, '{}'::jsonb)
                    || jsonb_build_object('member_count', cardinality(cleaned));
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_graph_communities_normalize
        BEFORE INSERT OR UPDATE ON graph_communities
        FOR EACH ROW EXECUTE FUNCTION graph_communities_normalize()
        """
    )


def create_workflow_domain() -> None:
    op.create_table(
        "workflow_graphs",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column(
            "status", sa.String(), nullable=False, server_default=sa.text("'draft'")
        ),
        sa.Column(
            "version", sa.String(), nullable=False, server_default=sa.text("'0.1.0'")
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "max_depth", sa.Integer(), nullable=False, server_default=sa.text("6")
        ),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "domain", "country_code", "version", name="uq_workflow_graphs_scope_version"
        ),
    )
    op.create_table(
        "workflow_versions",
        sa.Column("graph_id", sa.UUID(), nullable=False),
        sa.Column(
            "definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("from_version", sa.String(), nullable=True),
        sa.Column("to_version", sa.String(), nullable=True),
        sa.Column("change_log", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["graph_id"],
            ["workflow_graphs.id"],
            ondelete="CASCADE",
            name="fk_workflow_versions_graph",
        ),
    )

    op.create_table(
        "workflow_nodes",
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("node_key", sa.String(), nullable=False),
        sa.Column(
            "level", sa.String(), nullable=False, server_default=sa.text("'coarse'")
        ),
        sa.Column("path", LtreeType(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "preconditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("tool_hints", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("artifacts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["workflow_versions.id"],
            ondelete="CASCADE",
            name="fk_workflow_nodes_version",
        ),
        sa.UniqueConstraint(
            "version_id", "node_key", name="uq_workflow_nodes_version_node_key"
        ),
    )
    op.create_index(
        "ix_workflow_nodes_version_path",
        "workflow_nodes",
        ["version_id", "path"],
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_nodes_path_gist
        ON workflow_nodes
        USING gist (path)
        """
    )

    op.create_table(
        "workflow_edges",
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("source_node_id", sa.UUID(), nullable=False),
        sa.Column("target_node_id", sa.UUID(), nullable=False),
        sa.Column(
            "transition_type",
            sa.String(),
            nullable=False,
            server_default=sa.text("'success'"),
        ),
        sa.Column("condition", sa.String(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["workflow_versions.id"],
            ondelete="CASCADE",
            name="fk_workflow_edges_version",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["workflow_nodes.id"],
            ondelete="CASCADE",
            name="fk_workflow_edges_source",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["workflow_nodes.id"],
            ondelete="CASCADE",
            name="fk_workflow_edges_target",
        ),
    )
    op.create_index(
        "ix_workflow_edges_version_source",
        "workflow_edges",
        ["version_id", "source_node_id"],
    )
    op.create_index(
        "ix_workflow_edges_version_target",
        "workflow_edges",
        ["version_id", "target_node_id"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION workflow_nodes_validate_depth()
        RETURNS TRIGGER AS $$
        DECLARE
            v_graph_id uuid;
            v_max_depth integer;
        BEGIN
            SELECT graph_id INTO v_graph_id
            FROM workflow_versions
            WHERE id = NEW.version_id;

            IF v_graph_id IS NULL THEN
                RAISE EXCEPTION 'Workflow version % has no parent graph', NEW.version_id;
            END IF;

            SELECT max_depth INTO v_max_depth
            FROM workflow_graphs
            WHERE id = v_graph_id;

            IF v_max_depth IS NULL THEN
                v_max_depth := 6;
            END IF;

            IF NEW.path IS NULL THEN
                RAISE EXCEPTION 'Path must be provided for workflow nodes';
            END IF;

            IF nlevel(NEW.path) > v_max_depth THEN
                RAISE EXCEPTION 'Path % exceeds max depth %', NEW.path, v_max_depth;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_workflow_nodes_validate_depth
        BEFORE INSERT OR UPDATE ON workflow_nodes
        FOR EACH ROW EXECUTE FUNCTION workflow_nodes_validate_depth()
        """
    )

    op.execute(
        """
        CREATE VIEW workflow_version_history AS
        SELECT
            v.id AS workflow_version_id,
            v.graph_id,
            g.name,
            g.domain,
            g.country_code,
            v.from_version,
            v.to_version,
            v.change_log,
            v.approved_by,
            v.approved_at,
            v.created_at
        FROM workflow_versions v
        JOIN workflow_graphs g ON g.id = v.graph_id;
        """
    )


def create_operational_views_and_triggers() -> None:
    op.create_table(
        "base_documents_by_country",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column(
            "country_code", sa.String(length=3), nullable=False, primary_key=True
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_base_documents_document",
        ),
        sa.UniqueConstraint(
            "document_id",
            "country_code",
            name="uq_base_documents_document",
        ),
        postgresql_partition_by="LIST (country_code)",
    )

    # Pre-create the partitions for every ISO-3 code so refresh cycles remain
    # lightweight even for newly onboarded regions.
    for country_code in ISO_ALPHA3_CODES:
        partition_name = f"base_documents_by_country_{country_code.lower()}"
        op.execute(
            f"""
            CREATE TABLE {partition_name}
            PARTITION OF base_documents_by_country
            FOR VALUES IN ('{country_code}')
            """
        )

    op.execute(
        """
        CREATE TABLE base_documents_by_country_default
        PARTITION OF base_documents_by_country
        DEFAULT
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION ensure_base_documents_partition(p_country_code text)
        RETURNS void AS $$
        DECLARE
            normalized text;
            partition_name text;
            exists boolean;
        BEGIN
            IF p_country_code IS NULL OR p_country_code = '' THEN
                RETURN;
            END IF;

            normalized := upper(p_country_code);
            partition_name := format('base_documents_by_country_%s', lower(normalized));

            SELECT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_inherits i ON c.oid = i.inhrelid
                JOIN pg_class p ON p.oid = i.inhparent
                WHERE p.relname = 'base_documents_by_country'
                  AND c.relname = partition_name
            ) INTO exists;

            IF NOT exists THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF base_documents_by_country FOR VALUES IN (''%s'')',
                    partition_name,
                    normalized
                );
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION refresh_base_documents_by_country(p_country_code text)
        RETURNS void AS $$
        DECLARE
            normalized text;
        BEGIN
            IF p_country_code IS NULL THEN
                FOR normalized IN
                    SELECT DISTINCT upper(country_code)
                    FROM documents
                    WHERE access_scope = 'base'
                      AND deleted_at IS NULL
                      AND country_code IS NOT NULL
                LOOP
                    PERFORM ensure_base_documents_partition(normalized);
                END LOOP;

                DELETE FROM base_documents_by_country;
                INSERT INTO base_documents_by_country (id, document_id, country_code, status, content_hash)
                SELECT gen_random_uuid(), id, country_code, status, content_hash
                FROM documents
                WHERE access_scope = 'base' AND deleted_at IS NULL;
            ELSE
                normalized := upper(p_country_code);
                PERFORM ensure_base_documents_partition(normalized);
                DELETE FROM base_documents_by_country WHERE country_code = normalized;
                INSERT INTO base_documents_by_country (id, document_id, country_code, status, content_hash)
                SELECT gen_random_uuid(), id, country_code, status, content_hash
                FROM documents
                WHERE access_scope = 'base'
                    AND deleted_at IS NULL
                    AND country_code = normalized;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE VIEW active_chunks AS
        SELECT
            c.id,
            c.document_id,
            c.chunk_type,
            c.country_code,
            c.position,
            c.text_content,
            c.image_caption,
            c.section_path,
            c.metadata,
            c.embedding,
            c.content_hash
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.status = 'active' AND d.deleted_at IS NULL;
        """
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW graph_edge_evidence_rollup AS
        SELECT
            edge_id,
            array_agg(chunk_id ORDER BY chunk_id) AS evidence_chunk_ids,
            COUNT(chunk_id) AS evidence_count,
            now() AS last_refreshed_at
        FROM graph_evidence
        GROUP BY edge_id;
        """
    )
    op.create_index(
        "ix_graph_edge_evidence_rollup_edge_id",
        "graph_edge_evidence_rollup",
        ["edge_id"],
    )
    op.execute(
        "CREATE INDEX ix_graph_edge_evidence_rollup_evidence_chunk_ids ON graph_edge_evidence_rollup USING GIN (evidence_chunk_ids)"
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW graph_hot_entities AS
        WITH counts AS (
            SELECT
                e.id,
                e.name,
                e.entity_type,
                e.country_code,
                COUNT(ge.id) AS edge_count
            FROM graph_entities e
            LEFT JOIN graph_edges ge
                ON e.id = ge.source_entity_id OR e.id = ge.target_entity_id
            GROUP BY e.id, e.name, e.entity_type, e.country_code
        )
        SELECT
            id,
            name,
            entity_type,
            country_code,
            edge_count,
            ROW_NUMBER() OVER (
                PARTITION BY country_code
                ORDER BY edge_count DESC, id
            ) AS hot_rank
        FROM counts;
        """
    )
    op.create_index(
        "ix_graph_hot_entities_country_code",
        "graph_hot_entities",
        ["country_code"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION refresh_graph_materializations(p_concurrently boolean DEFAULT false)
        RETURNS void AS $$
        DECLARE
            concurrent text := CASE WHEN p_concurrently THEN 'CONCURRENTLY' ELSE '' END;
        BEGIN
            EXECUTE format('REFRESH MATERIALIZED VIEW %s graph_edge_evidence_rollup', concurrent);
            EXECUTE format('REFRESH MATERIALIZED VIEW %s graph_hot_entities', concurrent);
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_update_document_chat_refs() RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.deleted_at IS NULL THEN
                    UPDATE documents
                    SET active_chat_refs = active_chat_refs + 1
                    WHERE id = NEW.document_id;
                END IF;
                RETURN NEW;
            ELSIF TG_OP = 'UPDATE' THEN
                IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
                    UPDATE documents
                    SET active_chat_refs = GREATEST(active_chat_refs - 1, 0)
                    WHERE id = NEW.document_id;
                ELSIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
                    UPDATE documents
                    SET active_chat_refs = active_chat_refs + 1
                    WHERE id = NEW.document_id;
                END IF;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                IF OLD.deleted_at IS NULL THEN
                    UPDATE documents
                    SET active_chat_refs = GREATEST(active_chat_refs - 1, 0)
                    WHERE id = OLD.document_id;
                END IF;
                RETURN OLD;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_update_document_chat_refs
        AFTER INSERT OR UPDATE OR DELETE ON conversation_documents
        FOR EACH ROW EXECUTE FUNCTION fn_update_document_chat_refs()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_sync_child_document_fields() RETURNS TRIGGER AS $$
        DECLARE
            doc_record RECORD;
        BEGIN
            SELECT content_hash, owner_user_id, country_code
            INTO doc_record
            FROM documents
            WHERE id = NEW.document_id;

            IF doc_record IS NULL THEN
                RAISE EXCEPTION 'Document % not found for child row', NEW.document_id;
            END IF;

            NEW.content_hash := doc_record.content_hash;

            IF TG_TABLE_NAME = 'chunks' THEN
                NEW.owner_user_id := doc_record.owner_user_id;
                NEW.country_code := COALESCE(doc_record.country_code, 'UNK');
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sync_artifacts_content_hash
        BEFORE INSERT OR UPDATE ON artifacts
        FOR EACH ROW EXECUTE FUNCTION fn_sync_child_document_fields()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sync_chunks_content_hash
        BEFORE INSERT OR UPDATE ON chunks
        FOR EACH ROW EXECUTE FUNCTION fn_sync_child_document_fields()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_sync_chunk_reference_country()
        RETURNS TRIGGER AS $$
        DECLARE
            v_country_code text;
        BEGIN
            IF NEW.chunk_id IS NULL THEN
                NEW.chunk_country_code := NULL;
                RETURN NEW;
            END IF;

            SELECT country_code INTO v_country_code
            FROM chunks
            WHERE id = NEW.chunk_id
            LIMIT 1;

            IF v_country_code IS NULL THEN
                RAISE EXCEPTION 'Chunk % not found for referencing row in %', NEW.chunk_id, TG_TABLE_NAME;
            END IF;

            NEW.chunk_country_code := v_country_code;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sync_message_citations_chunk_country
        BEFORE INSERT OR UPDATE ON message_citations
        FOR EACH ROW EXECUTE FUNCTION fn_sync_chunk_reference_country()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sync_chunk_metrics_country
        BEFORE INSERT OR UPDATE ON chunk_metrics
        FOR EACH ROW EXECUTE FUNCTION fn_sync_chunk_reference_country()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sync_retrieval_run_items_country
        BEFORE INSERT OR UPDATE ON retrieval_run_items
        FOR EACH ROW EXECUTE FUNCTION fn_sync_chunk_reference_country()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sync_pillar_answer_sources_country
        BEFORE INSERT OR UPDATE ON pillar_answer_sources
        FOR EACH ROW EXECUTE FUNCTION fn_sync_chunk_reference_country()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sync_graph_entities_chunk_country
        BEFORE INSERT OR UPDATE ON graph_entities
        FOR EACH ROW EXECUTE FUNCTION fn_sync_chunk_reference_country()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sync_graph_evidence_chunk_country
        BEFORE INSERT OR UPDATE ON graph_evidence
        FOR EACH ROW EXECUTE FUNCTION fn_sync_chunk_reference_country()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION workflow_nodes_move_subtree(
            p_graph_id UUID,
            p_source_path ltree,
            p_target_parent_path ltree
        ) RETURNS VOID AS $$
        DECLARE
            v_version_id UUID;
            v_max_depth INTEGER;
            v_relative_start INTEGER;
            v_rows INTEGER;
        BEGIN
            SELECT id INTO v_version_id
            FROM workflow_versions
            WHERE graph_id = p_graph_id
            ORDER BY created_at DESC
            LIMIT 1;

            IF v_version_id IS NULL THEN
                RAISE EXCEPTION 'No workflow version found for graph %', p_graph_id;
            END IF;

            SELECT max_depth INTO v_max_depth FROM workflow_graphs WHERE id = p_graph_id;

            IF v_max_depth IS NULL THEN
                v_max_depth := 6;
            END IF;

            IF p_target_parent_path <@ p_source_path THEN
                RAISE EXCEPTION 'Cannot move subtree into its own descendant';
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM workflow_nodes
                WHERE version_id = v_version_id AND path = p_target_parent_path
            ) THEN
                RAISE EXCEPTION 'Target parent path % does not exist for graph %', p_target_parent_path, p_graph_id;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM workflow_nodes
                WHERE version_id = v_version_id AND path <@ p_source_path
            ) THEN
                RAISE EXCEPTION 'Source path % does not exist for graph %', p_source_path, p_graph_id;
            END IF;

            v_relative_start := GREATEST(nlevel(p_source_path) - 1, 0);

            IF EXISTS (
                SELECT 1
                FROM workflow_nodes
                WHERE version_id = v_version_id
                  AND path <@ p_source_path
                  AND (
                      nlevel(p_target_parent_path) + (nlevel(path) - v_relative_start)
                  ) > v_max_depth
            ) THEN
                RAISE EXCEPTION 'Move violates max_depth constraint';
            END IF;

            UPDATE workflow_nodes
            SET path = (
                p_target_parent_path ||
                subpath(path, v_relative_start)
            )::ltree
            WHERE version_id = v_version_id AND path <@ p_source_path;

            GET DIAGNOSTICS v_rows = ROW_COUNT;

            IF v_rows = 0 THEN
                RAISE EXCEPTION 'No nodes updated for source path %', p_source_path;
            END IF;

            IF EXISTS (
                SELECT 1 FROM workflow_nodes
                WHERE version_id = v_version_id AND nlevel(path) > v_max_depth
            ) THEN
                RAISE EXCEPTION 'Move violates max_depth constraint';
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_track_document_gc_events() RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF OLD.active_chat_refs > 0 AND NEW.active_chat_refs = 0 THEN
                    INSERT INTO document_gc_events (
                        id,
                        document_id,
                        event_type,
                        prev_active_chat_refs,
                        new_active_chat_refs,
                        metadata
                    ) VALUES (
                        gen_random_uuid(),
                        NEW.id,
                        'active_refs_zero',
                        OLD.active_chat_refs,
                        NEW.active_chat_refs,
                        jsonb_build_object('updated_at', now())
                    );
                END IF;

                IF COALESCE(OLD.deleted_at, to_timestamp(0)) IS DISTINCT FROM COALESCE(NEW.deleted_at, to_timestamp(0)) THEN
                    INSERT INTO document_gc_events (
                        id,
                        document_id,
                        event_type,
                        prev_active_chat_refs,
                        new_active_chat_refs,
                        metadata
                    ) VALUES (
                        gen_random_uuid(),
                        NEW.id,
                        'deleted_state_changed',
                        OLD.active_chat_refs,
                        NEW.active_chat_refs,
                        jsonb_build_object(
                            'previous_deleted_at', OLD.deleted_at,
                            'new_deleted_at', NEW.deleted_at
                        )
                    );
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_document_gc_events
        AFTER UPDATE ON documents
        FOR EACH ROW EXECUTE FUNCTION fn_track_document_gc_events()
        """
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_available_extensions WHERE name = 'pg_graphql'
            ) THEN
                CREATE EXTENSION IF NOT EXISTS pg_graphql;
            END IF;
        END;
        $$;
        """
    )

    create_documents_domain()
    create_retrieval_domain()
    create_conversations_domain()
    create_knowledge_graph_domain()
    create_workflow_domain()
    create_operational_views_and_triggers()


def downgrade() -> None:
    # Drop operational helpers
    op.execute("DROP TRIGGER IF EXISTS trg_sync_chunks_content_hash ON chunks")
    op.execute("DROP TRIGGER IF EXISTS trg_sync_artifacts_content_hash ON artifacts")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_sync_message_citations_chunk_country ON message_citations"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_sync_chunk_metrics_country ON chunk_metrics")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_sync_retrieval_run_items_country ON retrieval_run_items"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_sync_pillar_answer_sources_country ON pillar_answer_sources"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_sync_graph_entities_chunk_country ON graph_entities"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_sync_graph_evidence_chunk_country ON graph_evidence"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_update_document_chat_refs ON conversation_documents"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_conversation_documents_soft_delete ON conversation_documents"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_conversation_documents_soft_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_document_gc_events ON documents")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_workflow_nodes_validate_depth ON workflow_nodes"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS workflow_nodes_move_subtree(UUID, ltree, ltree)"
    )
    op.execute("DROP FUNCTION IF EXISTS workflow_nodes_validate_depth")
    op.execute("DROP FUNCTION IF EXISTS refresh_graph_materializations(boolean)")
    op.execute("DROP FUNCTION IF EXISTS ensure_base_documents_partition(text)")
    op.execute("DROP FUNCTION IF EXISTS fn_sync_chunk_reference_country")
    op.execute("DROP FUNCTION IF EXISTS fn_sync_child_document_fields")
    op.execute("DROP FUNCTION IF EXISTS fn_track_document_gc_events")
    op.execute("DROP FUNCTION IF EXISTS fn_update_document_chat_refs")
    op.execute("DROP FUNCTION IF EXISTS refresh_base_documents_by_country(text)")
    op.execute("DROP VIEW IF EXISTS workflow_version_history")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS graph_hot_entities")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS graph_edge_evidence_rollup")
    op.execute("DROP VIEW IF EXISTS active_chunks")
    op.drop_table("base_documents_by_country")

    # Workflow domain
    op.drop_index("ix_workflow_edges_version_target", table_name="workflow_edges")
    op.drop_index("ix_workflow_edges_version_source", table_name="workflow_edges")
    op.drop_table("workflow_edges")
    op.drop_index("ix_workflow_nodes_path_gist", table_name="workflow_nodes")
    op.drop_index("ix_workflow_nodes_version_path", table_name="workflow_nodes")
    op.drop_table("workflow_nodes")
    op.drop_table("workflow_versions")
    op.drop_table("workflow_graphs")

    # Knowledge graph domain
    op.execute(
        "DROP TRIGGER IF EXISTS trg_graph_communities_normalize ON graph_communities"
    )
    op.execute("DROP FUNCTION IF EXISTS graph_communities_normalize")
    op.drop_index("ix_graph_communities_entity_ids_gin", table_name="graph_communities")
    op.drop_index("ix_graph_communities_country_level", table_name="graph_communities")
    op.drop_table("graph_communities")
    op.drop_table("graph_evidence")
    op.drop_index("ix_graph_edges_seen_brin", table_name="graph_edges")
    op.drop_index("ix_graph_edges_target_type", table_name="graph_edges")
    op.drop_index("ix_graph_edges_source_type", table_name="graph_edges")
    op.drop_table("graph_edges")
    op.drop_index("ix_graph_entities_embedding_hnsw", table_name="graph_entities")
    op.drop_index("uq_graph_entities_user_scope", table_name="graph_entities")
    op.drop_index("uq_graph_entities_base_scope", table_name="graph_entities")
    op.drop_index("ix_graph_entities_labels_gin", table_name="graph_entities")
    op.drop_index("ix_graph_entities_document_id", table_name="graph_entities")
    op.drop_index("ix_graph_entities_name", table_name="graph_entities")
    op.drop_table("graph_entities")

    # Conversations domain
    op.drop_table("agent_state_checkpoints")
    op.drop_index("ix_message_citations_chunk", table_name="message_citations")
    op.drop_table("message_citations")
    op.drop_index("ix_message_tool_calls_message", table_name="message_tool_calls")
    op.drop_table("message_tool_calls")
    op.drop_index("ix_messages_conversation_ordinal", table_name="messages")
    op.drop_table("messages")
    op.drop_index(
        "ix_conversation_documents_attach_source", table_name="conversation_documents"
    )
    op.drop_index(
        "ix_conversation_documents_document_id", table_name="conversation_documents"
    )
    op.drop_table("conversation_documents")
    op.drop_table("conversations")

    # Retrieval domain
    op.drop_table("pillar_answer_sources")
    op.drop_index("ix_pillar_answers_country_pillar", table_name="pillar_answers")
    op.drop_index("uq_pillar_answers_owner_country_pillar", table_name="pillar_answers")
    op.drop_table("pillar_answers")
    op.drop_index("ix_retrieval_runs_document_scope_gin", table_name="retrieval_runs")
    op.drop_index("ix_retrieval_runs_created_at", table_name="retrieval_runs")
    op.drop_table("retrieval_run_items")
    op.drop_table("retrieval_runs")
    op.drop_index("ix_chunk_metrics_chunk_id", table_name="chunk_metrics")
    op.drop_table("chunk_metrics")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_ivfflat")
    op.drop_index("ix_chunks_created_at_brin", table_name="chunks")
    op.drop_index("ix_chunks_updated_at_brin", table_name="chunks")
    op.drop_index("ix_chunks_country_chunk_type", table_name="chunks")
    op.drop_index("ix_chunks_text_tsv_gin", table_name="chunks")
    op.drop_index("ix_chunks_document_position", table_name="chunks")
    op.drop_table("chunks")

    # Documents domain
    op.drop_index("ix_artifacts_metadata_gin", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_ingestion_jobs_status_filter", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_document_stage", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_document_gc_events_document", table_name="document_gc_events")
    op.drop_table("document_gc_events")
    op.drop_index("uq_documents_owner_canonical_name_active", table_name="documents")
    op.drop_index("uq_documents_base_country_hash", table_name="documents")
    op.drop_index("uq_documents_owner_content_hash_active", table_name="documents")
    op.drop_index("ix_documents_scope_country", table_name="documents")
    op.drop_index("ix_documents_status_updated_at", table_name="documents")
    op.drop_table("documents")

    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS ltree")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_available_extensions WHERE name = 'pg_graphql'
            ) THEN
                DROP EXTENSION IF EXISTS pg_graphql;
            END IF;
        END;
        $$;
        """
    )
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
