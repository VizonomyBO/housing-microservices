from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.reduced_scope_smoke

SERVICE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SERVICE_ROOT.parents[1]


def test_compose_file_declares_required_services() -> None:
    compose = REPO_ROOT / "docker-compose.yml"
    assert compose.exists(), "root docker-compose.yml is missing"
    data = yaml.safe_load(compose.read_text())
    services = data.get("services", {})
    for required in ("agent-api", "postgres", "db-init"):
        assert required in services, f"{required} not found in docker-compose.yml"

    agent_profiles = services["agent-api"].get("profiles", [])
    assert "reduced" in agent_profiles, "agent-api missing reduced profile"
    assert "full" in agent_profiles, "agent-api missing full profile"

    db_init_profiles = services["db-init"].get("profiles", [])
    assert "reduced" in db_init_profiles, "db-init missing reduced profile"


def test_seed_script_present_and_executable() -> None:
    script = SERVICE_ROOT / "scripts" / "seed_reduced_scope_data.py"
    assert script.exists(), "Seed script missing"
    text = script.read_text()
    assert "DEMO_DOCUMENTS" in text, "Seed script missing demo payload definition"


def test_smoke_verifier_script_present() -> None:
    script = SERVICE_ROOT / "scripts" / "verify_reduced_scope_compose.sh"
    assert script.exists(), "verify_reduced_scope_compose.sh missing"
    assert script.stat().st_mode & 0o111, "Smoke verifier script is not executable"
