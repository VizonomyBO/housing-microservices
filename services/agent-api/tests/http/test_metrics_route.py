from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_api.http import create_app
from telemetry.metrics_registry import get_metrics_registry


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_metrics_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METRICS_AUTH_TOKEN", "metrics-secret")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/metrics")
    assert response.status_code == 401
    assert response.json()["error"]["message"].startswith("Missing")


def test_metrics_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METRICS_AUTH_TOKEN", "metrics-secret")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/metrics", headers=_auth_header("wrong"))
    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Invalid metrics auth token"


def test_metrics_returns_prometheus_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "metrics-secret"
    monkeypatch.setenv("METRICS_AUTH_TOKEN", token)
    app = create_app()
    registry = get_metrics_registry()
    registry.record_hitl_event(event="pause", reason="low_confidence", route="informational")
    with TestClient(app) as client:
        response = client.get("/metrics", headers=_auth_header(token))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert "agent_hitl_events_total" in response.text
    assert response.headers["X-Accel-Buffering"] == "no"
    assert response.headers["Cache-Control"] == "no-store"
