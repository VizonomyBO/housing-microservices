from __future__ import annotations

import os
from pathlib import Path


def _load_env_prod() -> None:
    """Load critical settings from .env.prod without overriding explicit env vars."""

    root = Path(__file__).resolve().parents[3]
    env_path = root / ".env.prod"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        name, _, raw_value = line.partition("=")
        key = name.strip()
        value = raw_value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


# Force evals to use the local app with prod settings + data by default.
os.environ.setdefault("EVAL_USE_LOCAL_APP", "1")
_load_env_prod()

# Ensure the runner has the basics available for auth/LLM.
if "AUTH_SHARED_SECRET" in os.environ:
    os.environ.setdefault("EVAL_AUTH_SECRET", os.environ["AUTH_SHARED_SECRET"])
if "AGENT_BASE_URL" in os.environ:
    os.environ.setdefault("EVAL_BASE_URL", os.environ["AGENT_BASE_URL"])
# Prefer HS256 shared-secret validation for local eval app runs.
os.environ.setdefault("AUTH_JWKS_URL", "")

# Force DATABASE_URL to the prod value and coerce to asyncpg so local app runs
# against the real data instead of the ephemeral test container.
db_url = os.environ.get("DATABASE_URL")
if db_url:
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    os.environ["DATABASE_URL"] = db_url
