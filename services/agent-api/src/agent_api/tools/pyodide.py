"""Pyodide sandbox helper."""

from __future__ import annotations

import httpx

from agent_api.settings import PyodideConfig


async def execute_in_pyodide(
    *,
    code: str,
    packages: list[str],
    request_id: str | None,
    config: PyodideConfig | None = None,
) -> dict:
    if config is None or not config.base_url:
        raise RuntimeError("PYODIDE_BASE_URL not configured; sandbox execution is unavailable.")

    url = config.base_url.rstrip("/") + "/execute"
    payload = {"code": code, "packages": packages, "request_id": request_id}
    timeout = httpx.Timeout(config.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


__all__ = ["execute_in_pyodide"]
