from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from shared_data_layer.db.models import ChatResponseCache
from shared_data_layer.db.session import DatabaseSessionManager
from shared_data_layer.repositories.documents import DocumentRepository, DocumentUploadRepository
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.runner import LangGraphRunner
from agent_api.auth.validator import AuthContext
from agent_api.http.context import RequestContext
from agent_api.http.schemas import ChatConstraints, ChatMessagePayload, ResponseMode
from agent_api.models.chat import ChatRequestContext
from agent_api.report_cache import delete_cached_report, upload_cached_report
from agent_api.services.conversations import ConversationService
from agent_api.services.preprocessing import PILLAR_QUESTIONS, _is_cacheable_answer
from agent_api.services.reports import ReportService
from agent_api.settings import Settings, load_settings

logger = logging.getLogger(__name__)

_SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"
_DEFAULT_POLL_INTERVAL_SECONDS = 10


def _hash_question(question: str) -> str:
    from agent_api.services.cache import ChatCacheService

    return ChatCacheService._hash_question(question)


class ReprocessWorker:
    def __init__(self, settings: Settings, runner: LangGraphRunner) -> None:
        self._settings = settings
        self._runner = runner
        self._poll_interval = _DEFAULT_POLL_INTERVAL_SECONDS

    async def run_forever(self) -> None:
        if not self._settings.database_url:
            raise RuntimeError("DATABASE_URL is required for worker mode")
        DatabaseSessionManager.init(self._settings.database_url)
        try:
            while True:
                processed = await self._process_once()
                await asyncio.sleep(1 if processed > 0 else self._poll_interval)
        finally:
            await DatabaseSessionManager.dispose()

    async def _process_once(self) -> int:
        async with DatabaseSessionManager.session() as session:
            upload_repo = DocumentUploadRepository(session)
            claimed_upload = await upload_repo.claim_next_queued_upload(
                claimed_at=datetime.now(UTC)
            )
            if claimed_upload is None:
                return 0
            upload_id = claimed_upload.id

        try:
            await self._process_upload(upload_id)
        except Exception:
            logger.exception("worker.upload.unhandled upload_id=%s", upload_id)
        return 1

    async def _process_upload(self, upload_id: UUID) -> None:
        async with DatabaseSessionManager.session() as session:
            upload_repo = DocumentUploadRepository(session)
            upload = await upload_repo.get_upload(upload_id)
            if upload is None:
                return
            country_code = upload.country_code

        logger.info("worker.upload.start upload_id=%s country=%s", upload_id, country_code)
        try:
            await self._run_ingestion_for_upload(upload_id)
            await self._reprocess_country_cache(country_code)

            async with DatabaseSessionManager.session() as session:
                upload_repo = DocumentUploadRepository(session)
                await upload_repo.update_reprocess_status(
                    upload_id=upload_id,
                    status="reprocessing_pdf",
                    error=None,
                )
                await session.commit()

            await self._reprocess_country_pdf(country_code)

            completed_at = datetime.now(UTC)
            async with DatabaseSessionManager.session() as session:
                upload_repo = DocumentUploadRepository(session)
                await upload_repo.update_reprocess_status(
                    upload_id=upload_id,
                    status="done",
                    error=None,
                    completed_at=completed_at,
                )
                await session.commit()
            logger.info("worker.upload.done upload_id=%s country=%s", upload_id, country_code)
        except Exception as exc:
            logger.exception("worker.upload.failed upload_id=%s country=%s", upload_id, country_code)
            failed_at = datetime.now(UTC)
            async with DatabaseSessionManager.session() as session:
                upload_repo = DocumentUploadRepository(session)
                await upload_repo.update_reprocess_status(
                    upload_id=upload_id,
                    status="failed",
                    error=str(exc),
                    completed_at=failed_at,
                )
                await session.commit()

    async def _run_ingestion_for_upload(self, upload_id: UUID) -> None:
        internal_secret = self._settings.auth.shared_secret
        if internal_secret is None or internal_secret.strip() == "":
            raise RuntimeError("AUTH_SHARED_SECRET or JWT_SECRET_KEY is required for worker ingestion")
        ingest_base_url = self._settings.ingestion_base_url.rstrip("/")
        endpoint = f"{ingest_base_url}/v1/internal/admin/documents/{upload_id}/ingest"
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                endpoint,
                headers={"X-Worker-Secret": internal_secret},
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Background ingestion failed for upload {upload_id}: "
                f"status={response.status_code} body={response.text}"
            )
        payload = response.json()
        upload_payload = payload.get("upload")
        if not isinstance(upload_payload, dict):
            raise RuntimeError(f"Background ingestion returned invalid payload for upload {upload_id}")
        document_id = upload_payload.get("document_id")
        if document_id is None:
            raise RuntimeError(f"Background ingestion did not attach document for upload {upload_id}")

    async def _reprocess_country_cache(self, country_code: str) -> None:
        async with DatabaseSessionManager.session() as session:
            conversation_service = ConversationService(session)
            document_repo = DocumentRepository(session)
            documents = await document_repo.list_documents_for_country(country_code)
            if not documents:
                return

            conversation = await conversation_service.ensure_conversation(
                owner_user_id=_SYSTEM_USER_ID,
                country_code=country_code,
                title=f"Reprocessing - {country_code}",
                namespace="reprocessing",
                tags=["reprocessing", country_code],
            )
            for document in documents:
                await document_repo.attach_to_conversation(
                    conversation_id=conversation.id,
                    document_id=document.id,
                    attach_source="reprocessing",
                    visibility_override="hidden",
                )
            await session.commit()
            conversation_id = str(conversation.id)

        for questions in PILLAR_QUESTIONS.values():
            for question in questions:
                await self._reprocess_question(
                    country_code=country_code,
                    conversation_id=conversation_id,
                    question=question,
                )

    async def _reprocess_question(
        self,
        *,
        country_code: str,
        conversation_id: str,
        question: str,
    ) -> None:
        question_hash = _hash_question(question)
        async with DatabaseSessionManager.session() as session:
            existing_entry = await self._get_cache_entry(session, country_code, question_hash)
            if existing_entry is not None:
                existing_entry.status = "reprocessing"
                await session.commit()

        response_data = await self._generate_question_response(
            country_code=country_code,
            conversation_id=conversation_id,
            question=question,
        )

        if response_data is None:
            async with DatabaseSessionManager.session() as session:
                existing_entry = await self._get_cache_entry(session, country_code, question_hash)
                if existing_entry is not None:
                    existing_entry.status = "stale"
                    await session.commit()
            return

        async with DatabaseSessionManager.session() as session:
            await session.execute(
                delete(ChatResponseCache).where(
                    ChatResponseCache.country_code == country_code,
                    ChatResponseCache.question_hash == question_hash,
                )
            )
            session.add(
                ChatResponseCache(
                    country_code=country_code,
                    question=question,
                    question_hash=question_hash,
                    response=response_data,
                    status="ready",
                )
            )
            await session.commit()

    async def _generate_question_response(
        self,
        *,
        country_code: str,
        conversation_id: str,
        question: str,
    ) -> dict[str, object] | None:
        auth = AuthContext(user_id=None, tenant_id=None, roles=None, scopes=None, metadata=None)
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            request_context = RequestContext(
                request_id=f"worker-{country_code}-{uuid4()}-a{attempt}",
                traceparent=None,
                idempotency_key=None,
                headers={},
            )
            chat_request = ChatRequestContext(
                conversation_id=conversation_id,
                thread_id=str(uuid4()),
                session_id=None,
                allow_stateless=False,
                message=ChatMessagePayload(content=question),
                hints={"retrieval_profile": "country_profile"},
                constraints=ChatConstraints(country_code=country_code),
                owner_user_id=_SYSTEM_USER_ID,
                workspace_id=None,
                tenant_id=None,
            )
            async with DatabaseSessionManager.session() as session:
                try:
                    result = await self._runner.run_chat(
                        request=chat_request,
                        auth=auth,
                        request_context=request_context,
                        sse_emitter=None,
                        prompt_overrides={},
                        hints={"retrieval_profile": "country_profile"},
                        response_mode=ResponseMode.BLOCKING,
                        db_session=session,
                    )
                except Exception:
                    logger.exception(
                        "worker.question.error country=%s attempt=%s", country_code, attempt
                    )
                    continue
                if not result or not result.done_payload:
                    continue
                done_payload = result.done_payload
                valid, _ = _is_cacheable_answer(
                    str(done_payload.get("answer", "")),
                    done_payload.get("citations"),
                )
                if not valid:
                    continue
                return {
                    "thread_id": chat_request.thread_id,
                    "request_id": request_context.request_id,
                    "done": done_payload,
                    "messages": result.messages or [],
                }
        return None

    async def _reprocess_country_pdf(self, country_code: str) -> None:
        async with DatabaseSessionManager.session() as session:
            report_service = ReportService(
                db_session=session,
                runner=self._runner,
                settings=self._settings,
            )
            pdf_bytes = await report_service.generate_housing_report(
                country_code=country_code,
                user_id=_SYSTEM_USER_ID,
                request_context=RequestContext(
                    request_id=f"worker-report-{country_code}-{uuid4()}",
                    traceparent=None,
                    idempotency_key=None,
                    headers={},
                ),
                auth_context=AuthContext(
                    user_id=None,
                    tenant_id=None,
                    roles=None,
                    scopes=None,
                    metadata=None,
                ),
                skip_cache=True,
                upload_cache=False,
            )
            delete_cached_report(country_code, self._settings)
            upload_cached_report(country_code, pdf_bytes, self._settings)

    async def _get_cache_entry(
        self, session: AsyncSession, country_code: str, question_hash: str
    ) -> ChatResponseCache | None:
        result = await session.execute(
            select(ChatResponseCache).where(
                ChatResponseCache.country_code == country_code,
                ChatResponseCache.question_hash == question_hash,
            )
        )
        return result.scalar_one_or_none()


async def run_worker_forever() -> None:
    settings = load_settings()
    runner = LangGraphRunner(settings=settings)
    worker = ReprocessWorker(settings=settings, runner=runner)
    await worker.run_forever()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker_forever())


if __name__ == "__main__":
    main()
