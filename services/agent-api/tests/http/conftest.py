from __future__ import annotations

import pytest

from agent_api.http.context import AuthContext


@pytest.fixture(autouse=True)
def stub_auth_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the AuthTokenValidator so HTTP route tests can focus on business logic."""

    async def _fake_validate(self, token: str) -> AuthContext:  # pragma: no cover - helper
        return AuthContext(
            user_id=token,
            tenant_id=token,
            roles=["test"],
            scopes=["agent-api:test"],
            metadata={"claims": {"sub": token}},
        )

    monkeypatch.setattr(
        "agent_api.auth.jwt_validator.AuthTokenValidator.validate",
        _fake_validate,
        raising=False,
    )
