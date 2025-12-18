"""Pyodide sandbox helper."""

from __future__ import annotations

from agent_api.settings import PyodideConfig
from agent_api.tools.local_pyodide import PyodideSandbox


async def execute_in_pyodide(
    *,
    code: str,
    packages: list[str],
    request_id: str | None,
    config: PyodideConfig | None = None,
) -> dict:
    sandbox = PyodideSandbox(allow_net=True)
    result = await sandbox.execute(code, packages=packages or [])
    return {
        "result": result.result,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "status": result.status,
        "execution_time": getattr(result, "execution_time", None),
    }


__all__ = ["execute_in_pyodide"]
