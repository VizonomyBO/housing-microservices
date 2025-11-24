"""
Application entry point for the Auth Service (FastAPI).
"""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
