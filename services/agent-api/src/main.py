"""Uvicorn entrypoint for the Agent API."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI

from agent_api.http.app import create_app
from agent_api.settings import load_settings
from agent_api.worker import run_worker_forever

_settings = load_settings()

if _settings.service_mode == "worker":
    app = FastAPI(title="Agent Worker Mode", docs_url=None, redoc_url=None)
else:
    app = create_app()

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    if _settings.service_mode == "worker":
        asyncio.run(run_worker_forever())
    else:
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
