"""Pydantic schemas shared by retrieval nodes."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_api.reduced_scope import ReducedScopeFlags


class AttachmentType(str, Enum):
    """Attachment asset categories understood by retrieval nodes."""

    DOCUMENT = "document"
    WORKFLOW = "workflow"


class IncomingAttachment(BaseModel):
    """Raw attachment reference provided by the chat gateway."""

    model_config = ConfigDict(extra="allow")

    type: Literal["document_reference", "workflow_reference"] = Field(...)
    document_id: str | None = None
    workflow_id: str | None = None
    visibility: Literal["visible", "hidden", "read_only"] | None = Field(default=None)
    role: str | None = Field(default=None)
    attach_source: str | None = Field(default=None)

    @field_validator("document_id", mode="after")
    @classmethod
    def _require_document_id(cls, value: str | None, info):
        if info.data.get("type") == "document_reference" and not value:
            raise ValueError("document_reference attachments require document_id")
        return value

    @field_validator("workflow_id", mode="after")
    @classmethod
    def _require_workflow_id(cls, value: str | None, info):
        if info.data.get("type") == "workflow_reference" and not value:
            raise ValueError("workflow_reference attachments require workflow_id")
        return value


class ChatMessagePayload(BaseModel):
    """User-facing chat payload that seeds InputNormalizer."""

    type: Literal["user"] = Field(default="user")
    content: str
    attachments: list[IncomingAttachment] = Field(default_factory=list)


class ChatConstraints(BaseModel):
    """Chat-level knobs forwarded by the gateway."""

    country_code: str | None = None
    auto_attach_base_docs: bool = True
    max_tool_calls: int | None = None
    allowed_chunk_types: list[str] | None = None


class ChatRequestContext(BaseModel):
    """Complete gateway envelope delivered to InputNormalizer."""

    conversation_id: str
    thread_id: str
    session_id: str | None = None
    allow_stateless: bool = False
    message: ChatMessagePayload
    hints: dict[str, Any] = Field(default_factory=dict)
    constraints: ChatConstraints = Field(default_factory=ChatConstraints)
    owner_user_id: str | None = None
    workspace_id: str | None = None
    tenant_id: str | None = None
    reduced_scope: ReducedScopeFlags | None = None


class TenantScope(BaseModel):
    """Tenant metadata persisted after normalization for cache keys."""

    conversation_id: str
    thread_id: str
    session_id: str | None = None
    owner_user_id: str | None = None
    workspace_id: str | None = None
    tenant_id: str | None = None
    country_code: str | None = None


class AttachmentReference(BaseModel):
    """Normalized attachment reference exported by InputNormalizer."""

    asset_type: AttachmentType
    asset_id: str
    document_id: str | None = None
    workflow_id: str | None = None
    attach_source: str
    role: str | None = None
    visibility: Literal["visible", "hidden", "read_only"] = "visible"
    read_only: bool = False
    canonical_name: str | None = None
    access_scope: str | None = None
    country_code: str | None = None
    auto_attached: bool = False
    provided_in_request: bool = False

    @field_validator("document_id", mode="before")
    @classmethod
    def _default_document_id(cls, value: str | None, info):
        if value:
            return value
        asset_type: AttachmentType | None = info.data.get("asset_type")
        asset_id = info.data.get("asset_id")
        if asset_type == AttachmentType.DOCUMENT and asset_id:
            return asset_id
        return value

    @field_validator("workflow_id", mode="before")
    @classmethod
    def _default_workflow_id(cls, value: str | None, info):
        if value:
            return value
        asset_type: AttachmentType | None = info.data.get("asset_type")
        asset_id = info.data.get("asset_id")
        if asset_type == AttachmentType.WORKFLOW and asset_id:
            return asset_id
        return value


class NormalizedInput(BaseModel):
    """Primary output of the InputNormalizer node."""

    normalized_prompt: str
    raw_prompt: str
    language_code: str | None = None
    language_confidence: float | None = None
    intent_tags: list[str] = Field(default_factory=list)
    tenant_scope: TenantScope
    attachment_refs: list[AttachmentReference] = Field(default_factory=list)
    scope_hash: str
    warnings: list[str] = Field(default_factory=list)
    allowed_chunk_types: list[str] | None = Field(
        default=None,
        description="Chunk types permitted for retrieval when reduced scope limits apply.",
    )


class AttachmentDocumentChunk(BaseModel):
    """Chunk preview surfaced to downstream prompt builders."""

    chunk_id: str
    text: str
    page_number: int | None = None
    position: int | None = None


class AttachmentDocument(BaseModel):
    """Hydrated document scoped for retrieval."""

    document_id: str
    canonical_name: str | None = None
    access_scope: str
    language: str | None = None
    country_code: str | None = None
    tags: list[str] | None = None
    visibility: Literal["visible", "hidden", "read_only"] = "visible"
    read_only: bool = False
    auto_attached: bool = False
    metadata: dict[str, Any] | None = None
    chunks: list[AttachmentDocumentChunk] = Field(default_factory=list)


class AttachmentWorkflow(BaseModel):
    """Hydrated workflow referenced by attachments."""

    workflow_id: str
    name: str
    domain: str
    version: str
    status: str
    country_code: str | None = None
    metadata: dict[str, Any] | None = None


class AttachmentScope(BaseModel):
    """Output of AttachmentScopeLoader for downstream retrieval nodes."""

    documents: list[AttachmentDocument] = Field(default_factory=list)
    workflows: list[AttachmentWorkflow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_assets: list[str] = Field(default_factory=list)
