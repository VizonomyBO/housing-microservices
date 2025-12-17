"""FastAPI router for conversation lifecycle endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import get_auth_context, get_db_session, get_request_context
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import (
    AttachmentRecord,
    ConversationCreateRequest,
    ConversationListItem,
    ConversationListResponse,
    ConversationMessageResponse,
    ConversationPageInfo,
    ConversationRecordResponse,
    ConversationResponse,
    ConversationSummaryResponse,
    PaginationMetadata,
)
from agent_api.services.conversations import ConversationService
from agent_api.services.retrieval_scope import ConversationScopeRepository

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("", summary="List conversations for the authenticated user")
async def list_conversations(
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    tags: Annotated[
        list[str] | None,
        Query(description="Filters conversations that include all provided tags"),
    ] = None,
    country_code: Annotated[
        str | None,
        Query(description="ISO-3 country code filter"),
    ] = None,
) -> JSONResponse:
    user_id = _require_user(auth_context)
    service = ConversationService(db_session)
    rows, total_count = await service.list_conversations(
        owner_user_id=user_id,
        page=page,
        page_size=page_size,
        tags=tags or [],
        country_code=country_code,
    )
    scope_repo = ConversationScopeRepository(db_session)
    items: list[ConversationListItem] = []
    for row in rows:
        attachments = await scope_repo.list_conversation_documents(row.id)
        items.append(
            _to_list_schema(
                row,
                attachment_count=len(attachments),
            )
        )
    response = ConversationListResponse(
        conversations=items,
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_count=total_count,
            has_next=(page * page_size) < total_count,
        ),
        request_id=request_context.request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(mode="json"),
    )


@router.post("", summary="Create or reuse a conversation")
async def create_conversation(
    payload: ConversationCreateRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    user_id = _require_user(auth_context)
    service = ConversationService(db_session)
    result = await service.ensure_conversation(
        owner_user_id=user_id,
        country_code=payload.country_code,
        title=payload.title,
        namespace=payload.namespace,
        tags=payload.tags,
        metadata=payload.metadata,
    )
    await db_session.commit()
    response = ConversationResponse(
        conversation=_to_schema(result),
        request_id=request_context.request_id,
        created=True,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response.model_dump(mode="json"),
    )


@router.get("/{conversation_id}", summary="Fetch conversation metadata")
async def get_conversation(
    conversation_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    cursor: Annotated[str | None, Query(description="Pagination cursor")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JSONResponse:
    user_id = _require_user(auth_context)
    service = ConversationService(db_session)
    try:
        record = await service.fetch_conversation(
            conversation_id,
            owner_user_id=user_id,
        )
    except (PermissionError, LookupError) as exc:
        raise GatewayError(
            code="NOT_FOUND",
            message="Conversation not found",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc

    scope_repo = ConversationScopeRepository(db_session)
    attachments = await scope_repo.list_conversation_documents(record.id)
    messages, next_cursor, remaining = await service.list_messages(
        conversation_id=conversation_id,
        limit=limit,
        cursor=cursor,
    )
    response = ConversationResponse(
        conversation=_to_schema(record),
        attachments=[_attachment_to_schema(att) for att in attachments if att.is_visible],
        messages=[
            ConversationMessageResponse(
                message_id=str(message.id),
                role=message.role,  # type: ignore[arg-type]
                content=message.content,
                created_at=message.created_at,
                metadata=message.metadata_,
            )
            for message in messages
        ],
        page_info=ConversationPageInfo(
            next_cursor=next_cursor,
            remaining_count=remaining,
        ),
        request_id=request_context.request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(mode="json"),
    )


@router.get("/{conversation_id}/summary", summary="Summarize conversation activity")
async def get_conversation_summary(
    conversation_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    user_id = _require_user(auth_context)
    service = ConversationService(db_session)
    try:
        record = await service.fetch_conversation(
            conversation_id,
            owner_user_id=user_id,
        )
    except (PermissionError, LookupError) as exc:
        raise GatewayError(
            code="NOT_FOUND",
            message="Conversation not found",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc

    scope_repo = ConversationScopeRepository(db_session)
    attachments = await scope_repo.list_conversation_documents(record.id)
    messages, _, _ = await service.list_messages(
        conversation_id=conversation_id, limit=200, cursor=None
    )

    response = ConversationSummaryResponse(
        conversation_id=str(record.id),
        attachment_count=len(attachments),
        message_count=len(messages),
        user_prompt_count=len([m for m in messages if m.role == "user"]),
        last_message_at=messages[-1].created_at if messages else None,
        last_activity_at=messages[-1].created_at
        if messages
        else record.updated_at or record.created_at,
        request_id=request_context.request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(mode="json"),
    )


def _require_user(auth_context: AuthContext) -> str:
    if not auth_context.user_id:
        raise GatewayError(
            code="UNAUTHORIZED",
            message="Authentication required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return auth_context.user_id


def _attachment_to_schema(record) -> AttachmentRecord:
    return AttachmentRecord(
        document_id=record.document_id,
        attach_source=record.attach_source,
        role=record.role,
        visibility=record.visibility,
        canonical_name=record.canonical_name,
        access_scope=record.access_scope,
        country_code=record.country_code,
        metadata=record.metadata,
    )


def _to_schema(record) -> ConversationRecordResponse:
    metadata = record.metadata_ or {}
    tags = metadata.get("tags") or []
    namespace = metadata.get("namespace") or "default"
    return ConversationRecordResponse(
        conversation_id=str(record.id),
        owner_user_id=str(record.owner_user_id) if record.owner_user_id else None,
        namespace=namespace,
        title=record.title,
        country_code=record.country_code,
        status=record.status,
        tags=tags,
        metadata=record.metadata_,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_list_schema(record, attachment_count: int) -> ConversationListItem:
    metadata = record.metadata_ or {}
    tags = metadata.get("tags") or []
    namespace = metadata.get("namespace") or "default"
    return ConversationListItem(
        conversation_id=str(record.id),
        owner_user_id=str(record.owner_user_id) if record.owner_user_id else None,
        namespace=namespace,
        title=record.title,
        country_code=record.country_code,
        status=record.status,
        tags=tags,
        document_count=attachment_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_activity_at=record.updated_at or record.created_at,
    )


__all__ = ["router"]
