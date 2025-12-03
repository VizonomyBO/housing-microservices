"""HTTP-facing Pydantic schemas for the FastAPI gateway."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from agent_api.reduced_scope import ReducedScopeFlags
from models.retrieval import (
    ChatConstraints,
    ChatMessagePayload,
    ChatRequestContext,
    IncomingAttachment,
)


class ResponseMode(str, Enum):
    """Controls whether the HTTP response streams or blocks."""

    STREAM = "stream"
    BLOCKING = "blocking"


class ChatMessageBody(ChatMessagePayload):
    """Extends the retrieval ChatMessagePayload for HTTP inputs."""

    attachments: list[IncomingAttachment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_user_message(self) -> ChatMessageBody:
        if self.type != "user":
            raise ValueError("POST /v1/chat requires message.type='user'")
        return self


class ChatRequestBody(BaseModel):
    """Incoming request body for POST /v1/chat."""

    thread_id: str | None = Field(default=None, description="Existing thread identifier")
    session_id: str | None = Field(default=None, description="Logical session grouping id")
    message: ChatMessageBody
    hints: dict[str, Any] = Field(default_factory=dict)
    prompt_overrides: dict[str, Any] = Field(default_factory=dict)
    response_mode: ResponseMode | None = Field(
        default=None,
        description="Preferred response style (streaming vs blocking)",
    )
    stream: bool | None = Field(
        default=None,
        description="Legacy boolean alias for response_mode; true=stream",
    )
    constraints: ChatConstraints = Field(default_factory=ChatConstraints)

    def resolved_response_mode(self) -> ResponseMode:
        """Resolve the response mode, honoring the legacy stream flag."""

        if self.response_mode is not None:
            return self.response_mode
        if self.stream is not None:
            return ResponseMode.STREAM if self.stream else ResponseMode.BLOCKING
        return ResponseMode.STREAM

    def to_request_context(
        self,
        *,
        conversation_id: str,
        owner_user_id: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        allowed_chunk_types: Iterable[str] | None = None,
        reduced_scope_flags: ReducedScopeFlags | None = None,
    ) -> ChatRequestContext:
        """Convert the HTTP payload into the internal ChatRequestContext."""

        message_payload = ChatMessagePayload.model_validate(self.message.model_dump())
        constraints = self.constraints.model_copy(deep=True)
        if allowed_chunk_types is not None:
            constraints.allowed_chunk_types = list(allowed_chunk_types)
        return ChatRequestContext(
            conversation_id=conversation_id,
            thread_id=conversation_id,
            session_id=self.session_id,
            message=message_payload,
            hints=dict(self.hints or {}),
            constraints=constraints,
            owner_user_id=owner_user_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            reduced_scope=reduced_scope_flags,
        )


class BlockingChatResponse(BaseModel):
    """JSON structure returned when clients opt out of streaming."""

    thread_id: str
    request_id: str
    done: dict[str, Any]
    messages: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "AttachmentDeleteResponse",
    "AttachmentListResponse",
    "AttachmentMutationResponse",
    "AttachmentRecord",
    "AttachmentRequest",
    "BlockingChatResponse",
    "ChatMessageBody",
    "ChatRequestBody",
    "ConversationCreateRequest",
    "ConversationRecordResponse",
    "ConversationResponse",
    "DemoPurgeDocumentsRequest",
    "DemoPurgeDocumentsResponse",
    "DemoResetConversationRequest",
    "DemoResetConversationResponse",
    "DocumentUploadRequest",
    "DocumentUploadResponse",
    "PillarAnswerPayload",
    "PillarResponse",
    "PillarSourcePayload",
    "ResponseMode",
]


class DocumentUploadRequest(BaseModel):
    """Payload for POST /v1/documents/upload in reduced-scope mode."""

    document_name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    content_type: Literal["text/markdown"] = Field(default="text/markdown")
    chunk_type: Literal["text", "image", "table"] = Field(default="text")
    access_scope: Literal["user_private", "user_shared", "base"] = Field(default="user_private")
    country_code: str | None = Field(
        default=None,
        description="ISO-3 country code required for base documents.",
    )
    language: str | None = Field(default=None, description="ISO 639-1 language code")
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    owner_user_id: str | None = Field(
        default=None,
        description="Optional UUID override; defaults to auth context.",
    )

    @model_validator(mode="after")
    def _validate_country_code(self) -> DocumentUploadRequest:
        if not self.document_name.strip():
            raise ValueError("document_name must contain visible characters")
        self.document_name = self.document_name.strip()
        if self.country_code:
            code = self.country_code.strip().upper()
            if len(code) != 3:
                raise ValueError("country_code must be a 3-letter ISO code")
            self.country_code = code
        if self.owner_user_id:
            try:
                UUID(str(self.owner_user_id))
            except ValueError as exc:  # pragma: no cover - defensive guard
                raise ValueError("owner_user_id must be a UUID string") from exc
        if self.chunk_type not in {"text", "image", "table"}:
            raise ValueError("chunk_type is invalid")
        return self


class DocumentUploadResponse(BaseModel):
    """Response payload for POST /v1/documents/upload."""

    document_id: str | None = None
    ingestion_id: str | None = None
    content_hash: str
    status: Literal["COMPLETED", "DEDUPED", "FEATURE_DISABLED"]
    message: str | None = None
    request_id: str
    upload: dict[str, Any] | None = None
    ingestion: dict[str, Any] | None = None
    reduced_scope: dict[str, Any] | None = None


class DemoResetConversationRequest(BaseModel):
    """Payload for POST /v1/demo/reset-conversation."""

    conversation_id: str | None = Field(
        default=None,
        description="Target conversation. Defaults to deterministic reduced-e2e slug.",
    )
    namespace: str | None = Field(
        default="reduced-e2e",
        description="Namespace used when deriving the deterministic conversation id.",
    )

    @model_validator(mode="after")
    def _validate_fields(self) -> DemoResetConversationRequest:
        if self.conversation_id:
            self.conversation_id = self.conversation_id.strip()
            if not self.conversation_id:
                self.conversation_id = None
        if self.namespace:
            self.namespace = self.namespace.strip() or "reduced-e2e"
        return self


class DemoResetConversationResponse(BaseModel):
    """Response payload for POST /v1/demo/reset-conversation."""

    conversation_id: str
    detached_documents: int
    deleted_messages: int
    deleted_checkpoints: int
    deleted_agent_runs: int
    request_id: str
    reduced_scope: dict[str, Any] | None = None


class DemoPurgeDocumentsRequest(BaseModel):
    """Payload for POST /v1/demo/purge-documents."""

    document_aliases: list[str] = Field(
        default_factory=list,
        description="Optional fixture aliases that should be purged (case-insensitive).",
    )
    content_hashes: list[str] = Field(
        default_factory=list,
        description="Optional SHA-256 hashes to purge. When omitted, purges all user docs.",
    )

    @model_validator(mode="after")
    def _normalize_lists(self) -> DemoPurgeDocumentsRequest:
        aliases = {alias.strip().upper() for alias in self.document_aliases if alias.strip()}
        hashes: set[str] = set()
        for value in self.content_hashes:
            if not value:
                continue
            normalized = value.strip().lower()
            if normalized and len(normalized) == 64:
                try:
                    int(normalized, 16)
                except ValueError as exc:
                    raise ValueError("content_hashes must be hexadecimal strings") from exc
                hashes.add(normalized)
            else:
                raise ValueError("content_hashes must be 64-character hex strings")
        self.document_aliases = sorted(aliases)
        self.content_hashes = sorted(hashes)
        return self


class DemoPurgeDocumentsResponse(BaseModel):
    """Response payload for POST /v1/demo/purge-documents."""

    purged_documents: int
    document_ids: list[str] = Field(default_factory=list)
    content_hashes: list[str] = Field(default_factory=list)
    request_id: str
    reduced_scope: dict[str, Any] | None = None


class ConversationCreateRequest(BaseModel):
    """Payload for POST /v1/conversations."""

    title: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, description="ISO-3 country code")
    namespace: str | None = Field(default="reduced-e2e", max_length=64)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = Field(default=None)

    @model_validator(mode="after")
    def _normalize_fields(self) -> ConversationCreateRequest:
        if self.title is not None:
            stripped = self.title.strip()
            self.title = stripped or None
        if self.country_code:
            code = self.country_code.strip().upper()
            if len(code) != 3:
                raise ValueError("country_code must be a 3-letter ISO code")
            self.country_code = code
        if self.namespace is not None:
            self.namespace = self.namespace.strip() or None
        cleaned_tags: list[str] = []
        tag_keys: set[str] = set()
        for tag in self.tags:
            if not tag:
                continue
            trimmed = tag.strip()
            key = trimmed.lower()
            if trimmed and key not in tag_keys:
                tag_keys.add(key)
                cleaned_tags.append(trimmed)
        self.tags = cleaned_tags
        return self


class ConversationRecordResponse(BaseModel):
    """Response body representing a conversation."""

    conversation_id: str
    owner_user_id: str | None = None
    namespace: str
    title: str | None = None
    country_code: str | None = None
    status: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ConversationResponse(BaseModel):
    """Envelope returned by create/read endpoints."""

    conversation: ConversationRecordResponse
    request_id: str
    created: bool | None = None
    reduced_scope: dict[str, Any] | None = None


class AttachmentRecord(BaseModel):
    document_id: str
    attach_source: str
    role: str
    visibility: Literal["visible", "hidden", "read_only"]
    canonical_name: str | None = None
    access_scope: str
    country_code: str | None = None
    metadata: dict[str, Any] | None = None


class AttachmentListResponse(BaseModel):
    conversation_id: str
    attachments: list[AttachmentRecord]
    request_id: str


class AttachmentRequest(BaseModel):
    document_id: str
    visibility: Literal["visible", "hidden", "read_only"] | None = None
    role: str | None = Field(default="primary")
    auto_attach_base_docs: bool = False


class AttachmentMutationResponse(BaseModel):
    conversation_id: str
    document_id: str | None
    status: Literal["ATTACHED", "FEATURE_DISABLED", "NOT_FOUND"]
    attachment: AttachmentRecord | None = None
    auto_attached: list[str] = Field(default_factory=list)
    message: str | None = None
    request_id: str
    reduced_scope: dict[str, Any] | None = None


class AttachmentDeleteResponse(BaseModel):
    conversation_id: str
    document_id: str
    status: Literal["DETACHED", "NOT_FOUND", "FORBIDDEN"]
    request_id: str


class PillarSourcePayload(BaseModel):
    chunk_id: str
    document_id: str | None = None
    chunk_type: str | None = None
    evidence_text: str
    page_number: int | None = None


class PillarAnswerPayload(BaseModel):
    pillar: str
    score: float | None = None
    summary_markdown: str
    answer_json: dict[str, Any]
    document_id: str
    generated_at: datetime | None = None
    sources: list[PillarSourcePayload] = Field(default_factory=list)


class PillarResponse(BaseModel):
    country_code: str
    conversation_id: str | None = None
    pillars: list[PillarAnswerPayload]
    request_id: str
    reduced_scope: dict[str, Any] | None = None
