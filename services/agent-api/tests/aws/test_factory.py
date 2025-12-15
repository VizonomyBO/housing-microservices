from __future__ import annotations

import pytest

from agent_api.aws.factory import AWSClientFactory
from agent_api.settings import load_settings


class _DummySession:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.calls: list[dict[str, object]] = []

    def client(self, service_name: str, **kwargs):  # pragma: no cover - simple recorder
        info = {"service": service_name, **kwargs}
        self.calls.append(info)
        return info


@pytest.fixture
def dummy_session(monkeypatch: pytest.MonkeyPatch) -> dict[str, _DummySession]:
    holder: dict[str, _DummySession] = {}

    def _factory(**kwargs):
        session = _DummySession(**kwargs)
        holder["session"] = session
        return session

    monkeypatch.setattr("boto3.session.Session", _factory)
    return holder


def _override_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_factory_routes_clients_to_localstack(monkeypatch: pytest.MonkeyPatch, dummy_session):
    _override_env(
        monkeypatch,
        USE_LOCALSTACK="1",
        LOCALSTACK_HOST="localstack-test",
        LOCALSTACK_EDGE_PORT="4570",
    )
    settings = load_settings()
    factory = AWSClientFactory(settings=settings)

    client_info = factory.client("s3")
    session = dummy_session["session"]
    assert session.init_kwargs["aws_access_key_id"] == settings.aws_access_key_id
    assert client_info["endpoint_url"] == "http://localstack-test:4570"


def test_factory_omits_endpoint_when_using_real_aws(monkeypatch: pytest.MonkeyPatch, dummy_session):
    _override_env(
        monkeypatch,
        USE_LOCALSTACK="0",
        AWS_ACCESS_KEY_ID="real-ak",
        AWS_SECRET_ACCESS_KEY="real-sk",
        AWS_ENDPOINT_URL="",
    )
    settings = load_settings()
    factory = AWSClientFactory(settings=settings)

    client_info = factory.client("sqs")
    assert client_info["endpoint_url"] is None
    session = dummy_session["session"]
    assert session.init_kwargs["aws_access_key_id"] == "real-ak"
