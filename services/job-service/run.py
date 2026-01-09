#!/usr/bin/env python3
"""Convenience entry point for local development."""

import sys
from pathlib import Path

# Add src to path for local development
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from main import *

if __name__ == "__main__":
    import uvicorn
    from job_service.settings import load_settings

    settings = load_settings()
    uvicorn.run(
        "job_service.main:app",
        host="0.0.0.0",
        port=settings.http_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )

