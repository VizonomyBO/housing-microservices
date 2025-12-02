"""InputNormalizer node implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models.retrieval import (
    AttachmentReference,
    AttachmentType,
    ChatRequestContext,
    NormalizedInput,
    TenantScope,
)
from nodes.retrieval.exceptions import (
    AttachmentValidationError,
    InputNormalizationError,
)
from nodes.retrieval.utils.hashing import compute_scope_hash
from nodes.retrieval.utils.language import LanguageDetectorProtocol
from nodes.retrieval.utils.text import normalize_prompt
from repositories.conversation_scope_repository import (
    ConversationDocumentRecord,
    ConversationScopePort,
)
from state.agent_state import AgentState
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, lifecycle_span


@dataclass(slots=True)
class InputNormalizerNode:
    """LangGraph node that validates chat payloads before retrieval."""

    request: ChatRequestContext
    scope_repository: ConversationScopePort
    language_detector: LanguageDetectorProtocol
    max_prompt_chars: int = 20000

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:  # pragma: no cover - exercised via tests
        conversation_id = state.conversation_id
        if not conversation_id:
            raise InputNormalizationError(
                code="CONVERSATION_ID_MISSING",
                message="Conversation id is required before normalization",
            )

        normalized_prompt = normalize_prompt(self.request.message.content)
        if not normalized_prompt:
            raise InputNormalizationError(
                code="EMPTY_PROMPT",
                message="User prompt is empty after trimming whitespace",
            )
        if len(normalized_prompt) > self.max_prompt_chars:
            raise InputNormalizationError(
                code="PROMPT_TOO_LARGE",
                message="User prompt exceeds maximum supported length",
                details={"max_chars": self.max_prompt_chars},
            )

        detection = self.language_detector.detect(normalized_prompt)
        tenant_scope = self._build_tenant_scope(state)
        metadata = {
            "country_code": tenant_scope.country_code,
            "auto_attach": self.request.constraints.auto_attach_base_docs,
        }

        async with lifecycle_span(
            emitter=sse_emitter,
            node="input_normalizer",
            subgraph="retrieval",
            metadata=metadata,
        ):
            conversation_docs = await self.scope_repository.list_conversation_documents(
                conversation_id
            )
            doc_map = {record.document_id: record for record in conversation_docs}

            auto_attached_ids = await self._auto_attach_base_docs(
                tenant_scope, doc_map, conversation_id
            )
            attachment_refs, warnings = self._materialize_attachment_refs(
                doc_map, auto_attached_ids
            )
            if auto_attached_ids:
                warnings.append(
                    f"Auto-attached {len(auto_attached_ids)} base document(s) for {tenant_scope.country_code}"
                )

            workflow_refs = [
                AttachmentReference(
                    asset_type=AttachmentType.WORKFLOW,
                    asset_id=attachment.workflow_id or "",
                    workflow_id=attachment.workflow_id,
                    attach_source=attachment.attach_source or "user_request",
                    provided_in_request=True,
                )
                for attachment in self.request.message.attachments
                if attachment.type == "workflow_reference"
            ]
            attachment_refs.extend(workflow_refs)
            add_metadata(
                attachment_count=len(attachment_refs),
                workflow_refs=len(workflow_refs),
                auto_attached=len(auto_attached_ids),
            )

            scope_hash_entries = [
                f"{ref.asset_type}:{ref.asset_id}:{ref.visibility}" for ref in attachment_refs
            ]
            scope_hash = compute_scope_hash(scope_hash_entries)

            normalized_input = NormalizedInput(
                normalized_prompt=normalized_prompt,
                raw_prompt=self.request.message.content,
                language_code=detection.language_code,
                language_confidence=detection.confidence,
                intent_tags=_flatten_intent_hints(self.request),
                tenant_scope=tenant_scope,
                attachment_refs=attachment_refs,
                scope_hash=scope_hash,
                warnings=warnings,
            )
            add_metadata(language=detection.language_code)
            return {"normalized_input": normalized_input}

    def _build_tenant_scope(self, state: AgentState) -> TenantScope:
        return TenantScope(
            conversation_id=state.conversation_id,
            thread_id=self.request.thread_id,
            session_id=self.request.session_id,
            owner_user_id=self.request.owner_user_id,
            workspace_id=self.request.workspace_id,
            tenant_id=self.request.tenant_id,
            country_code=self.request.constraints.country_code,
        )

    async def _auto_attach_base_docs(
        self,
        tenant_scope: TenantScope,
        doc_map: dict[str, ConversationDocumentRecord],
        conversation_id: str,
    ) -> set[str]:
        if not self.request.constraints.auto_attach_base_docs:
            return set()
        if not tenant_scope.country_code:
            return set()
        base_docs = await self.scope_repository.list_base_documents_for_country(
            tenant_scope.country_code
        )
        auto_attached: set[str] = set()
        for document in base_docs:
            if not document.auto_attach_enabled:
                continue
            if document.document_id in doc_map:
                continue
            record = await self.scope_repository.ensure_attachment(
                conversation_id=conversation_id,
                document_id=document.document_id,
                attach_source="base_auto",
            )
            doc_map[record.document_id] = record
            auto_attached.add(record.document_id)
        return auto_attached

    def _materialize_attachment_refs(
        self,
        doc_map: dict[str, ConversationDocumentRecord],
        auto_attached_ids: set[str],
    ) -> tuple[list[AttachmentReference], list[str]]:
        requested_doc_ids = {
            attachment.document_id
            for attachment in self.request.message.attachments
            if attachment.type == "document_reference" and attachment.document_id
        }
        missing = [doc_id for doc_id in requested_doc_ids if doc_id not in doc_map]
        if missing:
            raise AttachmentValidationError(
                code="ATTACHMENT_OUT_OF_SCOPE",
                message="Some attachments are not linked to this conversation",
                details={"document_ids": missing},
            )

        warnings: list[str] = []
        attachment_refs: list[AttachmentReference] = []
        for document_id in sorted(doc_map):
            record = doc_map[document_id]
            if not record.is_visible:
                if record.document_id in requested_doc_ids:
                    raise AttachmentValidationError(
                        code="ATTACHMENT_HIDDEN",
                        message="Requested attachment is hidden for this conversation",
                        details={"document_id": record.document_id},
                    )
                continue
            if record.read_only:
                warnings.append(f"Document {record.document_id} is read-only")
            attachment_refs.append(
                AttachmentReference(
                    asset_type=AttachmentType.DOCUMENT,
                    asset_id=record.document_id,
                    document_id=record.document_id,
                    attach_source=record.attach_source,
                    role=record.role,
                    visibility=record.visibility,
                    read_only=record.read_only,
                    canonical_name=record.canonical_name,
                    access_scope=record.access_scope,
                    country_code=record.country_code,
                    auto_attached=record.document_id in auto_attached_ids,
                    provided_in_request=record.document_id in requested_doc_ids,
                )
            )
        return attachment_refs, warnings


def _flatten_intent_hints(request: ChatRequestContext) -> list[str]:
    hints = []
    for key in sorted(request.hints):
        value = request.hints[key]
        if value is None:
            continue
        hints.append(f"{key}:{value}")
    return hints
