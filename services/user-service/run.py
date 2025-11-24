"""
ASGI entrypoint for running the FastAPI user-service.
"""

import os

import uvicorn


def main() -> None:
    port = int(os.getenv("PORT", 5001))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
