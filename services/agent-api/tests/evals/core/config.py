from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class EvalConfig:
    auth_base_url: str
    eval_user_email: str
    eval_user_password: str
    eval_user_id: str | None
    openai_model: str = "gpt-5.1"
    reasoning_effort: str = "high"

    @classmethod
    def from_env(cls) -> EvalConfig:
        return cls(
            auth_base_url=os.getenv("AUTH_BASE_URL") or "",  # type: ignore[arg-type]
            eval_user_email=os.getenv("EVAL_USER_EMAIL") or "",  # type: ignore[arg-type]
            eval_user_password=os.getenv("EVAL_USER_PASSWORD") or "",  # type: ignore[arg-type]
            eval_user_id=os.getenv("EVAL_USER_ID"),
            openai_model=os.getenv("EVAL_JUDGE_MODEL", "gpt-5.1"),
            reasoning_effort=os.getenv("EVAL_REASONING_EFFORT", "high"),
        )
