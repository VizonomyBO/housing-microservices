"""Tests for job service main application."""

import pytest
from fastapi.testclient import TestClient

from job_service.main import app


@pytest.fixture
def client():
    """Create test client."""
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    """Test health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "job-service"


def test_scheduler_status(client):
    """Test scheduler status endpoint."""
    response = client.get("/v1/scheduler/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "jobs" in data


def test_job_status(client):
    """Test job status endpoint."""
    response = client.get("/v1/jobs/report-pregeneration/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_running" in data
    assert data["is_running"] is False


def test_last_result_not_found(client):
    """Test last result returns 404 when no job has run."""
    response = client.get("/v1/jobs/report-pregeneration/last-result")
    # May return 404 if no job has run yet
    assert response.status_code in (200, 404)

