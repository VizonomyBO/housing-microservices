"""AttachmentScopeLoader node implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from models.retrieval import (
    AttachmentDocument,
    AttachmentDocumentChunk,
    AttachmentReference,
    AttachmentScope,
    AttachmentType,
    AttachmentWorkflow,
)
from nodes.retrieval.exceptions import InputNormalizationError
from repositories.conversation_scope_repository import (
    ConversationScopePort,
    DocumentChunkPreview,
    DocumentSummary,
)
from state.agent_state import AgentState
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, lifecycle_span


class WorkflowRepositoryProtocol(Protocol):
    async def get(self, workflow_id: UUID) -> Any: ...


@dataclass(slots=True)
class AttachmentScopeLoaderNode:
    """Hydrates documents/workflows referenced by InputNormalizer."""

    scope_repository: ConversationScopePort
    workflow_repository: WorkflowRepositoryProtocol | None = None
    preview_chunk_types: tuple[str, ...] = ("text",)
    max_preview_chars: int = 1600
    max_preview_chunks: int = 5

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        normalized_input = state.normalized_input
        if normalized_input is None:
            raise InputNormalizationError(
                code="NORMALIZED_INPUT_MISSING",
                message="InputNormalizer must run before AttachmentScopeLoader",
            )

        document_refs = [
            ref
            for ref in normalized_input.attachment_refs
            if ref.asset_type == AttachmentType.DOCUMENT
        ]
        workflow_refs = [
            ref
            for ref in normalized_input.attachment_refs
            if ref.asset_type == AttachmentType.WORKFLOW
        ]

        async with lifecycle_span(
            emitter=sse_emitter,
            node="attachment_scope_loader",
            subgraph="retrieval",
            metadata={
                "document_refs": len(document_refs),
                "workflow_refs": len(workflow_refs),
            },
        ):
            document_ids = [ref.document_id for ref in document_refs if ref.document_id]
            documents_lookup = await self.scope_repository.hydrate_documents(document_ids)
            chunk_previews = await self.scope_repository.load_document_chunk_previews(
                document_ids,
                chunk_types=self.preview_chunk_types,
                max_chars_per_doc=self.max_preview_chars,
                max_chunks_per_doc=self.max_preview_chunks,
            )

            warnings = list(normalized_input.warnings)
            missing_assets: list[str] = []
            documents = self._build_document_scope(
                document_refs,
                documents_lookup,
                chunk_previews,
                warnings,
                missing_assets,
            )
            workflows = await self._build_workflow_scope(workflow_refs, warnings, missing_assets)
            add_metadata(
                hydrated_documents=len(documents),
                hydrated_workflows=len(workflows),
                missing_assets=len(missing_assets),
            )

            scope = AttachmentScope(
                documents=sorted(documents, key=lambda doc: doc.document_id),
                workflows=sorted(workflows, key=lambda wf: wf.workflow_id),
                warnings=warnings,
                missing_assets=missing_assets,
            )
            return {"attachment_scope": scope}

    def _build_document_scope(
        self,
        references: list[AttachmentReference],
        documents_lookup: dict[str, DocumentSummary],
        chunk_previews: dict[str, list[DocumentChunkPreview]],
        warnings: list[str],
        missing_assets: list[str],
    ) -> list[AttachmentDocument]:
        documents: list[AttachmentDocument] = []
        for ref in references:
            if not ref.document_id:
                continue
            summary = documents_lookup.get(ref.document_id)
            if summary is None:
                missing_assets.append(ref.document_id)
                warnings.append(f"Document {ref.document_id} no longer exists or is unavailable")
                continue
            preview_chunks = [
                AttachmentDocumentChunk(
                    chunk_id=preview.chunk_id,
                    text=preview.text,
                    page_number=preview.page_number,
                    position=preview.position,
                )
                for preview in chunk_previews.get(ref.document_id, [])
            ]
            documents.append(
                AttachmentDocument(
                    document_id=summary.document_id,
                    canonical_name=summary.canonical_name,
                    access_scope=summary.access_scope,
                    language=summary.language,
                    country_code=summary.country_code,
                    tags=summary.tags,
                    visibility=ref.visibility,
                    read_only=ref.read_only,
                    auto_attached=ref.auto_attached,
                    metadata=summary.metadata,
                    chunks=preview_chunks,
                )
            )
        return documents

    async def _build_workflow_scope(
        self,
        references: list[AttachmentReference],
        warnings: list[str],
        missing_assets: list[str],
    ) -> list[AttachmentWorkflow]:
        if not references:
            return []
        if self.workflow_repository is None:
            warnings.append("Workflow repository not configured; skipping workflow attachments")
            return []

        workflows: list[AttachmentWorkflow] = []
        for ref in references:
            workflow_id = ref.workflow_id or ref.asset_id
            if not workflow_id:
                continue
            workflow = await self.workflow_repository.get(_as_uuid(workflow_id))
            if workflow is None:
                missing_assets.append(workflow_id)
                warnings.append(f"Workflow {workflow_id} not found")
                continue
            workflows.append(
                AttachmentWorkflow(
                    workflow_id=str(workflow.id),
                    name=workflow.name,
                    domain=workflow.domain,
                    version=workflow.version,
                    status=workflow.status,
                    country_code=workflow.country_code,
                    metadata=workflow.metadata_,
                )
            )
        return workflows


def _as_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
