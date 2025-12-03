from __future__ import annotations

import pytest

from agent_api.settings import load_settings

AWS_ENV_VARS = (
    "USE_LOCALSTACK",
    "AWS_ENDPOINT_URL",
    "LOCALSTACK_HOST",
    "LOCALSTACK_EDGE_PORT",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in AWS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_localstack_endpoint_is_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("USE_LOCALSTACK", "1")
    monkeypatch.setenv("LOCALSTACK_HOST", "localstack-test")
    monkeypatch.setenv("LOCALSTACK_EDGE_PORT", "4570")

    settings = load_settings()

    assert settings.aws_endpoint_url == "http://localstack-test:4570"
    assert settings.aws_access_key_id == "localstack"
    assert settings.aws_secret_access_key == "localstack"


def test_explicit_endpoint_overrides_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("USE_LOCALSTACK", "1")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://s3.us-east-1.amazonaws.com")

    settings = load_settings()

    assert settings.aws_endpoint_url == "https://s3.us-east-1.amazonaws.com"


def test_real_aws_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("USE_LOCALSTACK", "0")

    settings = load_settings()

    assert settings.aws_endpoint_url is None
    assert settings.aws_access_key_id is None
    assert settings.aws_secret_access_key is None
