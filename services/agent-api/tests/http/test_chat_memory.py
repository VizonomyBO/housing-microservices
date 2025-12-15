from __future__ import annotations

from contextlib import asynccontextmanager
from types import MethodType
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from agent_api.http import create_app
from agent_api.http.deps import get_chat_runner, set_chat_runner
from agent_api.http.schemas import ResponseMode
from cache import InMemoryValkeyClient
from nodes.retrieval.utils.language import StubLanguageDetector
from services.langgraph_runner import LangGraphChatRunner
from telemetry import CacheObservability, MetricsRegistry


@asynccontextmanager
async def _lifespan(app):
    async with app.router.lifespan_context(app):
        yield


TEST_HEADERS = lambda user_id: {"Authorization": f"Bearer {user_id}"}  # noqa: E731


@pytest.fixture
async def api_client(monkeypatch: pytest.MonkeyPatch, database_url: str):
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    monkeypatch.setenv("DATABASE_URL", async_url)
    app = create_app()
    async with _lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
def recording_runner(monkeypatch: pytest.MonkeyPatch):
    metrics = MetricsRegistry()
    runner = LangGraphChatRunner(
        cache_client=InMemoryValkeyClient(),
        cache_observability=CacheObservability(metrics=metrics, namespace="test"),
        language_detector=StubLanguageDetector(language_code="en", confidence=1.0),
        openai_client=None,
        metrics=metrics,
    )
    seen_message_counts: list[int] = []

    async def _fake_execute(self, state, context):  # type: ignore[override]
        seen_message_counts.append(len(state.messages))
        return state.model_copy(update={"answer": f"echo:{state.messages[-1].message.content}"})

    runner._execute_pipeline = MethodType(_fake_execute, runner)  # type: ignore[assignment]
    return runner, seen_message_counts


@pytest.fixture(autouse=True)
def _reset_runner():
    prev = get_chat_runner()
    yield
    set_chat_runner(prev)


@pytest.mark.asyncio
async def test_chat_persists_and_rehydrates_transcript(
    api_client: AsyncClient, recording_runner
) -> None:
    runner, seen_counts = recording_runner
    set_chat_runner(runner)

    user_id = str(uuid4())
    headers = TEST_HEADERS(user_id)

    conv_resp = await api_client.post("/v1/conversations", json={}, headers=headers)
    conversation_id = conv_resp.json()["conversation"]["conversation_id"]

    payload = {
        "thread_id": conversation_id,
        "message": {"type": "user", "content": "first turn", "attachments": []},
        "response_mode": ResponseMode.BLOCKING.value,
    }
    first = await api_client.post("/v1/chat", json=payload, headers=headers)
    assert first.status_code == 200

    follow_up = {
        "thread_id": conversation_id,
        "message": {"type": "user", "content": "second turn", "attachments": []},
        "response_mode": ResponseMode.BLOCKING.value,
    }
    second = await api_client.post("/v1/chat", json=follow_up, headers=headers)
    assert second.status_code == 200

    # Runner saw history on the second call (user + assistant + new user).
    assert seen_counts == [1, 3]

    conv_detail = await api_client.get(f"/v1/conversations/{conversation_id}", headers=headers)
    assert conv_detail.status_code == 200
    messages = conv_detail.json()["messages"]
    roles = [msg["role"] for msg in messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert messages[-1]["content"] == "echo:second turn"


@pytest.mark.asyncio
async def test_chat_rejects_foreign_conversation(api_client: AsyncClient, recording_runner) -> None:
    runner, _ = recording_runner
    set_chat_runner(runner)

    owner_id = str(uuid4())
    other_user_id = str(uuid4())
    conv_resp = await api_client.post("/v1/conversations", json={}, headers=TEST_HEADERS(owner_id))
    conversation_id = conv_resp.json()["conversation"]["conversation_id"]

    payload = {
        "thread_id": conversation_id,
        "message": {"type": "user", "content": "first turn", "attachments": []},
        "response_mode": ResponseMode.BLOCKING.value,
    }
    resp = await api_client.post("/v1/chat", json=payload, headers=TEST_HEADERS(other_user_id))

    assert resp.status_code == 404
