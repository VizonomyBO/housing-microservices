import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_api.agent.tool_runtime import ToolRuntime, set_runtime
from agent_api.agent.tools import compute_over_chunks


@pytest.mark.asyncio
async def test_compute_over_chunks_runs_pyodide(monkeypatch):
    # Prepare a fake retrieval context with a couple of chunks.
    chunk = SimpleNamespace(
        text="value: 10",
        score=0.9,
        page_number=1,
        position=0,
        document_id=str(uuid4()),
        canonical_name="doc",
    )
    ctx = SimpleNamespace(chunks=[chunk])

    captured_code: dict = {}

    async def fake_execute_in_pyodide(*, code, packages, request_id, config):
        captured_code["code"] = code
        return {"result": 20}

    monkeypatch.setattr("agent_api.agent.tools.execute_in_pyodide", fake_execute_in_pyodide)

    runtime = ToolRuntime(
        conversation_id=str(uuid4()),
        owner_user_id=str(uuid4()),
        auth=None,  # type: ignore[arg-type]
        db_session=None,  # type: ignore[arg-type]
        retrieval=None,  # type: ignore[arg-type]
        request_id="req-1",
        pyodide=SimpleNamespace(base_url="http://pyodide"),  # type: ignore[arg-type]
        last_retrieval=ctx,  # type: ignore[arg-type]
        metadata={},
    )
    set_runtime(runtime)

    user_code = "result = sum(1 for c in chunks if 'value' in c['text'])"
    payload = await compute_over_chunks.ainvoke({"python_code": user_code})  # type: ignore[typeddict-item]
    data = json.loads(payload)

    assert data["result"] == 20
    # Ensure the code injected the chunks variable.
    assert "chunks =" in captured_code["code"]
    assert "result" in captured_code["code"]
