from __future__ import annotations

import asyncio
import json

import pytest

from streaming.events import SSEEventType, TaskLifecyclePayload
from streaming.sse_emitter import SSEEmitter


@pytest.mark.asyncio
async def test_emit_formats_envelopes() -> None:
    emitter = SSEEmitter(conversation_id="conv-123", heartbeat_interval=0.5)
    payload = TaskLifecyclePayload(node="router", metadata={})
    await emitter.emit(event=SSEEventType.TASK_START, payload=payload)

    async def _consume() -> str:
        async for chunk in emitter.iter_sse():
            await emitter.close()
            return chunk
        raise AssertionError("Emitter did not yield data")

    chunk = await asyncio.wait_for(_consume(), timeout=0.5)
    lines = chunk.strip().splitlines()
    assert lines[0].startswith("id: ")
    assert lines[1] == "event: task_start"
    assert lines[2].startswith("data: ")
    payload_json = lines[2].split("data: ", 1)[1]
    body = json.loads(payload_json)
    assert body["event"] == "task_start"
    assert body["conversation_id"] == "conv-123"


@pytest.mark.asyncio
async def test_heartbeat_emitted_when_idle() -> None:
    emitter = SSEEmitter(conversation_id="conv-1", heartbeat_interval=0.05)

    async def _consume_heartbeat() -> str:
        gen = emitter.iter_sse()
        heartbeat = await asyncio.wait_for(gen.__anext__(), timeout=0.2)
        await emitter.close()
        return heartbeat

    chunk = await _consume_heartbeat()
    assert chunk.startswith(": keep-alive")


@pytest.mark.asyncio
async def test_queue_backpressure_drops_oldest() -> None:
    emitter = SSEEmitter(conversation_id="conv-drop", max_queue_size=1, heartbeat_interval=0.5)
    payload = TaskLifecyclePayload(node="router", metadata={})
    await emitter.emit(event=SSEEventType.TASK_START, payload=payload)
    await emitter.emit(event=SSEEventType.TASK_END, payload=payload)

    async def _consume_latest() -> str:
        async for chunk in emitter.iter_sse():
            await emitter.close()
            return chunk
        raise AssertionError("Emitter did not yield data")

    chunk = await asyncio.wait_for(_consume_latest(), timeout=0.5)
    assert "event: task_end" in chunk
    assert emitter.dropped_events == 1
