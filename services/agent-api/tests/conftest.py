import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from agent_api.auth.validator import AuthContext
from agent_api.http.app import create_app
from agent_api.http.deps import get_auth_context, get_runner
from agent_api.services.conversations import ConversationService
from agent_api.settings import Settings, load_settings


@pytest.fixture(scope="session")
def test_user_id() -> str:
    return str(uuid4())


@pytest.fixture(scope="session")
def configure_env(database_url: str, test_user_id: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "test-openai")
    os.environ["VOYAGE_API_KEY"] = os.environ.get("VOYAGE_API_KEY", "test-voyage")
    os.environ["INGEST_BASE_URL"] = os.environ.get("INGEST_BASE_URL", "http://example.com")
    os.environ["METRICS_AUTH_TOKEN"] = os.environ.get("METRICS_AUTH_TOKEN", "token")
    os.environ["AGENT_API_PORT"] = "8000"
    os.environ["STACK_PROFILE"] = "test"
    os.environ["SERVICE_MODE"] = "test"
    os.environ["AUTH_JWT_ALGORITHMS"] = "HS256"
    os.environ["AUTH_JWT_LEEWAY_SECONDS"] = "60"
    os.environ["AUTH_JWKS_CACHE_SECONDS"] = "60"


@dataclass(slots=True)
class ChatRunResult:
    done_payload: dict[str, Any]
    messages: list[dict[str, Any]] | None = None


class FakeRunner:
    async def run_chat(
        self,
        *,
        request,
        auth,
        request_context,
        sse_emitter,
        prompt_overrides,
        hints,
        response_mode,
        db_session,
    ) -> ChatRunResult:
        service = ConversationService(db_session)
        await service.append_message(
            conversation_id=request.conversation_id,
            role="user",
            content={"content": request.message.content},
        )
        await service.append_message(
            conversation_id=request.conversation_id,
            role="assistant",
            content={"content": "hello!", "citations": []},
        )
        await db_session.commit()
        return ChatRunResult(
            done_payload={
                "status": "COMPLETED",
                "answer": "hello!",
                "thread_id": request.thread_id,
                "route": "react",
                "citations": [],
                "requires_sql": False,
            },
            messages=[{"role": "assistant", "content": "hello!"}],
        )


@pytest.fixture
def app(
    configure_env: None,
    test_user_id: str,
    database_url: str,
    engine: AsyncEngine,
) -> FastAPI:
    settings = load_settings()
    DatabaseSessionManager.override_engine(engine)
    app = create_app()
    app.state.settings = settings
    app.state.db_initialized = True

    async def _fake_auth() -> AuthContext:
        return AuthContext(user_id=test_user_id, tenant_id=None, roles=[], scopes=[], metadata={})

    app.dependency_overrides[get_auth_context] = _fake_auth
    app.dependency_overrides[get_runner] = lambda: FakeRunner()
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="session")
def settings(configure_env: None) -> Settings:
    return load_settings()


@pytest.fixture(autouse=True)
async def clear_documents_table(
    app: FastAPI, session_factory: async_sessionmaker
) -> AsyncIterator[None]:
    yield
    async with session_factory() as session:
        await session.execute(text("TRUNCATE documents CASCADE"))
        await session.commit()
