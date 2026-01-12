"""HTTP-facing Pydantic schemas for the rebuilt Agent API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ResponseMode(str, Enum):
    STREAM = "stream"
    BLOCKING = "blocking"


class ChatMessagePayload(BaseModel):
    type: Literal["user"] = Field(default="user")
    content: str
    attachments: list[IncomingAttachment] = Field(default_factory=list)


class IncomingAttachment(BaseModel):
    type: Literal["document_reference", "workflow_reference"]
    document_id: str | None = None
    workflow_id: str | None = None
    visibility: Literal["visible", "hidden", "read_only"] | None = None
    role: str | None = None
    attach_source: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> IncomingAttachment:
        if self.type == "document_reference" and not self.document_id:
            raise ValueError("document_reference attachments require document_id")
        if self.type == "workflow_reference" and not self.workflow_id:
            raise ValueError("workflow_reference attachments require workflow_id")
        return self


class ChatConstraints(BaseModel):
    country_code: str | None = None
    auto_attach_base_docs: bool = True
    max_tool_calls: int | None = None
    allowed_chunk_types: list[str] | None = None


class ChatRequestBody(BaseModel):
    thread_id: str | None = Field(default=None, description="Existing thread identifier")
    session_id: str | None = Field(default=None, description="Logical session grouping id")
    message: ChatMessagePayload
    hints: dict[str, Any] = Field(default_factory=dict)
    prompt_overrides: dict[str, Any] = Field(default_factory=dict)
    response_mode: ResponseMode | None = Field(default=None)
    stream: bool | None = Field(default=None, description="Legacy boolean alias for response_mode")
    allow_stateless: bool = Field(default=False)
    constraints: ChatConstraints = Field(default_factory=ChatConstraints)
    use_cache: bool = Field(default=False, description="Use cached response if available for this country/question")

    def resolved_response_mode(self) -> ResponseMode:
        if self.response_mode is not None:
            return self.response_mode
        if self.stream is not None:
            return ResponseMode.STREAM if self.stream else ResponseMode.BLOCKING
        return ResponseMode.STREAM


class BlockingChatResponse(BaseModel):
    thread_id: str
    request_id: str
    done: dict[str, Any]
    messages: list[dict[str, Any]] = Field(default_factory=list)


class PaginationMetadata(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_count: int = Field(ge=0)
    has_next: bool


class DocumentListItem(BaseModel):
    document_id: str
    canonical_name: str
    access_scope: str
    country_code: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: str
    ingestion_stage: str | None = None
    ingestion_started_at: datetime | None = None
    ingestion_completed_at: datetime | None = None
    content_hash: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    pagination: PaginationMetadata
    request_id: str


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, description="ISO-3 country code")
    namespace: str | None = Field(default="default")
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
            self.namespace = (self.namespace or "").strip() or "default"
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


class ConversationMessageResponse(BaseModel):
    message_id: str
    role: Literal["system", "user", "assistant", "tool"]
    content: Any
    created_at: datetime
    metadata: dict[str, Any] | None = None


class ConversationPageInfo(BaseModel):
    next_cursor: str | None = None
    remaining_count: int = 0


class ConversationResponse(BaseModel):
    conversation: ConversationRecordResponse
    attachments: list[AttachmentRecord] = Field(default_factory=list)
    messages: list[ConversationMessageResponse] = Field(default_factory=list)
    page_info: ConversationPageInfo | None = None
    request_id: str
    created: bool | None = None


class ConversationListItem(BaseModel):
    conversation_id: str
    owner_user_id: str | None = None
    namespace: str
    title: str | None = None
    country_code: str | None = None
    status: str
    tags: list[str] = Field(default_factory=list)
    document_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None
    last_activity_at: datetime | None = None


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem]
    pagination: PaginationMetadata
    request_id: str


class ConversationSummaryResponse(BaseModel):
    conversation_id: str
    attachment_count: int
    message_count: int
    user_prompt_count: int
    last_message_at: datetime | None = None
    last_activity_at: datetime | None = None
    request_id: str


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


class AttachmentBulkRequest(BaseModel):
    document_ids: list[str] = Field(..., min_length=1, max_length=500)
    visibility: Literal["visible", "hidden", "read_only"] | None = None
    role: str | None = Field(default="primary")


class AttachmentBulkSkipped(BaseModel):
    document_id: str
    reason: str


class AttachmentBulkResponse(BaseModel):
    conversation_id: str
    attached: list[str] = Field(default_factory=list)
    skipped: list[AttachmentBulkSkipped] = Field(default_factory=list)
    request_id: str


class AttachmentMutationResponse(BaseModel):
    conversation_id: str
    document_id: str | None
    status: Literal["ATTACHED", "FEATURE_DISABLED", "NOT_FOUND"]
    attachment: AttachmentRecord | None = None
    auto_attached: list[str] = Field(default_factory=list)
    message: str | None = None
    request_id: str


class AttachmentDeleteResponse(BaseModel):
    conversation_id: str
    document_id: str
    status: Literal["DETACHED", "NOT_FOUND", "FORBIDDEN"]
    request_id: str


__all__ = [
    "AttachmentBulkRequest",
    "AttachmentBulkResponse",
    "AttachmentBulkSkipped",
    "AttachmentDeleteResponse",
    "AttachmentListResponse",
    "AttachmentMutationResponse",
    "AttachmentRecord",
    "AttachmentRequest",
    "BlockingChatResponse",
    "ChatConstraints",
    "ChatMessagePayload",
    "ChatRequestBody",
    "ConversationCreateRequest",
    "ConversationListItem",
    "ConversationListResponse",
    "ConversationMessageResponse",
    "ConversationPageInfo",
    "ConversationRecordResponse",
    "ConversationResponse",
    "ConversationSummaryResponse",
    "DocumentListItem",
    "DocumentListResponse",
    "IncomingAttachment",
    "PaginationMetadata",
    "ResponseMode",
]
