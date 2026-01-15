"""Entry point for the job service."""

import uvicorn

from job_service.main import app
from job_service.settings import load_settings

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.http_port,
        log_level=settings.log_level.lower(),
    )
