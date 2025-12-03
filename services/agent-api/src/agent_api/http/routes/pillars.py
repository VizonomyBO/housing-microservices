"""FastAPI router for synchronous pillar responses."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import RequestContext
from agent_api.http.deps import (
    get_db_session,
    get_rate_limiter,
    get_reduced_scope_runtime,
    get_request_context,
    get_settings,
)
from agent_api.http.errors import GatewayError
from agent_api.http.rate_limit import RateLimiterProtocol
from agent_api.http.schemas import (
    PillarAnswerPayload,
    PillarResponse,
    PillarSourcePayload,
)
from agent_api.reduced_scope import reduced_scope_demo_metadata
from agent_api.settings import Settings
from services import PillarAnswerDTO, PillarService, PillarSourceDTO, ReducedScopeWorkerRuntime

router = APIRouter(prefix="/v1", tags=["pillars"])


@router.get("/pillars/{country_code}", summary="List pillar answers for a country")
async def get_country_pillars(
    country_code: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    runtime: Annotated[ReducedScopeWorkerRuntime, Depends(get_reduced_scope_runtime)],
) -> JSONResponse:  # pragma: no cover - exercised via HTTP tests
    await runtime.generate_pillar_answers(country_code=country_code)
    service = PillarService(
        db_session,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    answers = await service.list_for_country(country_code)
    response = _build_response(
        answers,
        country_code=country_code.upper(),
        conversation_id=None,
        request_context=request_context,
        settings=settings,
    )
    headers = _build_headers(rate_limiter, settings)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(mode="json"),
        headers=headers,
    )


@router.get(
    "/conversations/{conversation_id}/pillars", summary="List pillar answers for a conversation"
)
async def get_conversation_pillars(
    conversation_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    runtime: Annotated[ReducedScopeWorkerRuntime, Depends(get_reduced_scope_runtime)],
) -> JSONResponse:
    service = PillarService(
        db_session,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    try:
        await runtime.generate_pillar_answers(conversation_id=conversation_id)
        convo_result = await service.list_for_conversation(conversation_id)
    except LookupError as exc:
        raise GatewayError(
            code="NOT_FOUND",
            message=str(exc),
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc
    response = _build_response(
        convo_result.answers,
        country_code=(convo_result.country_code or ""),
        conversation_id=conversation_id,
        request_context=request_context,
        settings=settings,
    )
    headers = _build_headers(rate_limiter, settings)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(mode="json"),
        headers=headers,
    )


def _build_response(
    answers: list[PillarAnswerDTO],
    *,
    country_code: str,
    conversation_id: str | None,
    request_context: RequestContext,
    settings: Settings,
) -> PillarResponse:
    reduced_scope_meta = (
        reduced_scope_demo_metadata(settings.reduced_scope)
        if settings.reduced_scope.is_enabled()
        else None
    )
    payloads = [_dto_to_payload(answer) for answer in answers]
    return PillarResponse(
        country_code=country_code,
        conversation_id=conversation_id,
        pillars=payloads,
        request_id=request_context.request_id,
        reduced_scope=reduced_scope_meta,
    )


def _dto_to_payload(answer: PillarAnswerDTO) -> PillarAnswerPayload:
    return PillarAnswerPayload(
        pillar=answer.pillar,
        score=answer.score,
        summary_markdown=answer.summary_markdown,
        answer_json=answer.answer_json,
        document_id=answer.document_id,
        generated_at=answer.generated_at,
        sources=[_source_to_payload(source) for source in answer.sources],
    )


def _source_to_payload(source: PillarSourceDTO) -> PillarSourcePayload:
    return PillarSourcePayload(
        chunk_id=source.chunk_id,
        document_id=source.document_id,
        chunk_type=source.chunk_type,
        evidence_text=source.evidence_text,
        page_number=source.page_number,
    )


def _build_headers(
    rate_limiter: RateLimiterProtocol,
    settings: Settings,
) -> dict[str, str]:
    headers = dict(rate_limiter.response_headers())
    if settings.reduced_scope.text_only_mode():
        headers.setdefault("X-Cache-Mode", "text-only")
        headers.setdefault("Viz-Demo-Mode", "text-only")
    return headers


__all__ = ["router"]
