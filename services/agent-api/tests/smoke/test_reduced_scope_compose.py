from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.reduced_scope_smoke

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_compose_file_declares_required_services() -> None:
    compose = PROJECT_ROOT / "docker-compose.reduced.yml"
    assert compose.exists(), "docker-compose.reduced.yml is missing"
    content = compose.read_text()
    for required in ("agent-api:", "postgres:", "db-init:"):
        assert required in content, f"{required} not found in compose file"


def test_seed_script_present_and_executable() -> None:
    script = PROJECT_ROOT / "scripts" / "seed_reduced_scope_data.py"
    assert script.exists(), "Seed script missing"
    text = script.read_text()
    assert "DEMO_DOCUMENTS" in text, "Seed script missing demo payload definition"


def test_smoke_verifier_script_present() -> None:
    script = PROJECT_ROOT / "scripts" / "verify_reduced_scope_compose.sh"
    assert script.exists(), "verify_reduced_scope_compose.sh missing"
    assert script.stat().st_mode & 0o111, "Smoke verifier script is not executable"
