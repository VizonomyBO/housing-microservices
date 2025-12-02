from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from agent_api.http import create_app
from agent_api.http.deps import set_chat_runner
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import ResponseMode
from agent_api.http.streaming import ChatRunnerProtocol, ChatRunResult
from streaming.events import SSEEventType, TaskLifecyclePayload
from streaming.sse_emitter import SSEEmitter


class _SuccessfulRunner(ChatRunnerProtocol):
    async def run_chat(
        self,
        *,
        request,
        auth,
        request_context,
        sse_emitter: SSEEmitter | None,
        prompt_overrides,
        hints,
        response_mode: ResponseMode,
        metrics,
        cache_observability,
        db_session,
    ) -> ChatRunResult:
        if sse_emitter is not None:
            payload = TaskLifecyclePayload(node="router", metadata={})
            await sse_emitter.emit(event=SSEEventType.TASK_START, payload=payload)
            await sse_emitter.emit(event=SSEEventType.TASK_END, payload=payload)
        done = {
            "status": "COMPLETED",
            "answer": "42",
            "cache_hit": False,
        }
        return ChatRunResult(done_payload=done, messages=[{"role": "assistant", "content": "42"}])


class _FailingRunner(ChatRunnerProtocol):
    async def run_chat(
        self,
        *,
        request,
        auth,
        request_context,
        sse_emitter: SSEEmitter | None,
        prompt_overrides,
        hints,
        response_mode: ResponseMode,
        metrics,
        cache_observability,
        db_session,
    ) -> ChatRunResult:
        raise GatewayError(code="INTERNAL_ERROR", message="boom", status_code=500)


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "thread_id": "thr_test",
        "session_id": "sess-1",
        "message": {
            "type": "user",
            "content": "hello",
            "attachments": [],
        },
        "hints": {},
        "prompt_overrides": {},
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def _reset_runner() -> Iterator[None]:
    set_chat_runner(_SuccessfulRunner())
    yield
    set_chat_runner(_SuccessfulRunner())


def test_streaming_endpoint_emits_sse_frames() -> None:
    app = create_app()
    client = TestClient(app)

    with client.stream("POST", "/v1/chat", json=_payload()) as response:
        chunks = list(response.iter_lines())

    assert response.status_code == 200
    assert any("event: meta" in chunk for chunk in chunks)
    assert any("event: task_start" in chunk for chunk in chunks)
    assert any("event: done" in chunk for chunk in chunks)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["X-Accel-Buffering"] == "no"


def test_blocking_mode_returns_json_payload() -> None:
    app = create_app()
    client = TestClient(app)

    payload = _payload(response_mode="blocking")
    response = client.post("/v1/chat", json=payload)
    data = response.json()
    assert response.status_code == 200
    assert data["done"]["status"] == "COMPLETED"
    assert response.headers["Cache-Control"] == "no-store"


def test_streaming_error_emits_task_error_event() -> None:
    set_chat_runner(_FailingRunner())
    app = create_app()
    client = TestClient(app)

    with client.stream("POST", "/v1/chat", json=_payload()) as response:
        chunks = list(response.iter_lines())

    assert any("event: task_error" in chunk for chunk in chunks)
    assert response.status_code == 500
