"""
Database models for document management.

Enums aligned with database_schema_persistence_rules.md and 001_create_documents_table.sql
"""

from enum import Enum


class DocumentStatus(str, Enum):
    """
    Document lifecycle status enum.

    Per database_schema_persistence_rules.md Section 3.2:
    - PENDING_UPLOAD: Awaiting file upload to S3
    - registered: Initial record created
    - validating: Preflight validation in progress
    - ingesting: Processing through pipeline
    - active: Successfully processed and available
    - failed: Processing failed
    - archived: Soft-deleted/archived
    """

    PENDING_UPLOAD = "PENDING_UPLOAD"
    REGISTERED = "registered"
    VALIDATING = "validating"
    INGESTING = "ingesting"
    ACTIVE = "active"
    FAILED = "failed"
    ARCHIVED = "archived"


class AccessScope(str, Enum):
    """
    Document access scope enum.

    Per database_schema_persistence_rules.md:
    - base: Shared corpus, country-scoped, owner_user_id IS NULL
    - user_private: Owner-only access
    - user_shared: Owner can share with others
    """

    BASE = "base"
    USER_PRIVATE = "user_private"
    USER_SHARED = "user_shared"


class IngestionStage(str, Enum):
    """
    Ingestion pipeline stages.

    Per database_schema_persistence_rules.md Section 3.2 and migration:
    - preflight: Validation, dedup check, artifact placeholder creation
    - convert: PDF/DOCX to Markdown/JSON conversion
    - chunk: Semantic chunking (~500 tokens)
    - embed: Vector embedding generation
    - index: Database indexing
    - activate: Final activation
    """

    PREFLIGHT = "preflight"
    CONVERT = "convert"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX = "index"
    ACTIVATE = "activate"


class Visibility(str, Enum):
    """
    Document visibility enum.

    Per database_schema_persistence_rules.md:
    - private: Owner only
    - shared: Shared with authorized users
    - base_admin: Base docs managed by admin
    """

    PRIVATE = "private"
    SHARED = "shared"
    BASE_ADMIN = "base_admin"


class ManagedBy(str, Enum):
    """
    Document management source.

    Per database_schema_persistence_rules.md:
    - user: User-uploaded document
    - system: System/pipeline managed
    - admin: Admin-uploaded base document
    """

    USER = "user"
    SYSTEM = "system"
    ADMIN = "admin"
