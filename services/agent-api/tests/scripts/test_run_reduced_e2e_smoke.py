from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from scripts.reduced_e2e_smoke.fixtures import ScenarioFixtures
from scripts.reduced_e2e_smoke.runner import SmokeRunConfig, run_smoke


@pytest.fixture
def respx_mock():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


class StubConversationProvider:
    def __init__(self, conversation_id: str = "conv-test") -> None:
        self.conversation_id = conversation_id
        self.calls: list[tuple[str, str]] = []

    async def ensure_conversation(self, *, owner_user_id: str, country_code: str) -> str:
        self.calls.append((owner_user_id, country_code))
        return self.conversation_id


def _mock_success_flows(
    respx_mock: respx.Router,
    *,
    fixtures: ScenarioFixtures,
    doc_ids: dict[str, str],
    prompt_answers: dict[str, str],
    conversation_id: str,
    include_demo_cleanup: bool = False,
    skip_main_flow: bool = False,
) -> None:
    document_fixtures = fixtures.documents()
    respx_mock.post("http://auth.test/v1/auth/register").mock(
        return_value=httpx.Response(201, json={"message": "ok", "user": {"id": "ignored"}})
    )
    respx_mock.post("http://auth.test/v1/auth/login").mock(
        return_value=httpx.Response(
            200,
            json={
                "user": {"id": "user-123"},
                "access_token": "token-abc",
                "refresh_token": "refresh-xyz",
            },
        )
    )

    respx_mock.post("http://agent.test/v1/conversations").mock(
        return_value=httpx.Response(
            201,
            json={
                "conversation": {
                    "conversation_id": conversation_id,
                    "owner_user_id": "user-123",
                    "namespace": "reduced-e2e",
                    "status": "active",
                    "tags": ["reduced_e2e", "demo"],
                },
                "created": True,
                "request_id": "req-conv",
            },
        )
    )

    pre_attachment_calls = 2 if include_demo_cleanup else 1
    convo_calls = {"count": 0}

    def conversation_list_handler(
        request: httpx.Request,
    ) -> httpx.Response:  # pragma: no cover - exercised via runner
        doc_count = len(doc_ids) if convo_calls["count"] >= pre_attachment_calls else 0
        convo_calls["count"] += 1
        return httpx.Response(
            200,
            json={
                "conversations": [
                    {
                        "conversation_id": conversation_id,
                        "owner_user_id": "user-123",
                        "namespace": "reduced-e2e",
                        "status": "active",
                        "tags": ["reduced_e2e", "demo"],
                        "document_count": doc_count,
                        "created_at": "2025-01-01T00:00:00Z",
                        "updated_at": "2025-01-01T00:00:00Z",
                        "last_activity_at": "2025-01-01T00:00:00Z",
                    }
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total_count": 1,
                    "has_next": False,
                },
                "request_id": "req-conv-list",
            },
        )

    respx_mock.get("http://agent.test/v1/conversations").mock(side_effect=conversation_list_handler)

    def document_list_handler(
        request: httpx.Request,
    ) -> httpx.Response:  # pragma: no cover - exercised via runner
        documents = [
            {
                "document_id": doc_ids[fixture.spec.alias],
                "canonical_name": fixture.spec.canonical_name,
                "access_scope": fixture.spec.access_scope,
                "country_code": fixture.spec.country_code,
                "language": fixture.spec.language,
                "tags": list(fixture.spec.tags),
                "status": "active",
                "ingestion_stage": "activate",
                "ingestion_started_at": "2025-01-01T00:00:00Z",
                "ingestion_completed_at": "2025-01-01T00:00:00Z",
                "content_hash": fixture.content_hash,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
                "metadata": {
                    "document_alias": fixture.spec.alias,
                },
            }
            for fixture in document_fixtures
        ]
        return httpx.Response(
            200,
            json={
                "documents": documents,
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total_count": len(documents),
                    "has_next": False,
                },
                "request_id": "req-doc-list",
            },
        )

    respx_mock.get("http://agent.test/v1/documents").mock(side_effect=document_list_handler)

    upload_iter = iter(document_fixtures)

    if not skip_main_flow:

        def upload_handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            fixture = next(upload_iter)
            alias = fixture.spec.alias
            return httpx.Response(
                201,
                json={
                    "document_id": doc_ids[alias],
                    "content_hash": fixture.content_hash,
                    "status": "COMPLETED",
                    "message": "ok",
                },
            )

        respx_mock.post("http://agent.test/v1/documents/upload").mock(side_effect=upload_handler)

        attachment_url = f"http://agent.test/v1/conversations/{conversation_id}/attachments"
        respx_mock.post(attachment_url).mock(
            return_value=httpx.Response(
                201,
                json={
                    "conversation_id": "conv-test",
                    "document_id": "placeholder",
                    "status": "ATTACHED",
                    "request_id": "req-attach",
                },
            )
        )

        attachment_listing = {
            "conversation_id": conversation_id,
            "request_id": "req-list",
            "attachments": [
                {
                    "document_id": doc_ids[fixture.spec.alias],
                    "attach_source": "user_request",
                    "role": "primary",
                    "visibility": "visible",
                    "canonical_name": fixture.spec.canonical_name,
                    "access_scope": fixture.spec.access_scope,
                    "country_code": fixture.spec.country_code,
                    "metadata": fixture.spec.metadata,
                }
                for fixture in document_fixtures
            ],
        }
        respx_mock.get(attachment_url).mock(
            return_value=httpx.Response(200, json=attachment_listing)
        )

        def chat_handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            body = json.loads(request.content.decode())
            prompt_id = body["hints"].get("prompt_id")
            answer = prompt_answers[prompt_id]
            doc_ids_for_prompt = [
                attachment["document_id"] for attachment in body["message"]["attachments"]
            ]
            done_payload = {
                "answer": answer,
                "citations": [{"document_id": doc_id} for doc_id in doc_ids_for_prompt],
            }
            if request.headers.get("accept") == "text/event-stream":
                sse = (
                    """event: meta\ndata: {\"ok\": true}\n\n"""
                    "event: done\ndata: " + json.dumps(done_payload) + "\n\n"
                )
                return httpx.Response(
                    200, content=sse, headers={"content-type": "text/event-stream"}
                )
            return httpx.Response(
                200, json={"done": done_payload, "messages": [{"content": answer}]}
            )

        respx_mock.post("http://agent.test/v1/chat").mock(side_effect=chat_handler)

        respx_mock.get(f"http://agent.test/v1/conversations/{conversation_id}/pillars").mock(
            return_value=httpx.Response(
                200,
                json={
                    "conversation_id": conversation_id,
                    "pillars": [],
                    "request_id": "req-pillars",
                },
            )
        )

    if include_demo_cleanup:
        respx_mock.post("http://agent.test/v1/demo/reset-conversation").mock(
            return_value=httpx.Response(
                200,
                json={
                    "conversation_id": conversation_id,
                    "detached_documents": 3,
                    "deleted_messages": 2,
                    "deleted_checkpoints": 1,
                    "deleted_agent_runs": 1,
                    "request_id": "req-reset",
                },
            )
        )
        respx_mock.post("http://agent.test/v1/demo/purge-documents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "purged_documents": 3,
                    "document_ids": ["doc-a", "doc-b", "doc-c"],
                    "content_hashes": ["hash-a"],
                    "request_id": "req-purge",
                },
            )
        )

    if skip_main_flow:
        return


def _prompt_answers(failing: bool = False) -> dict[str, str]:
    answers = {
        "Q_SIMPLE_QA": "Voucher expansion now serves five districts and caps rent at 32% of income.",
        "Q_REASON": "District 9 relief pulls ledger insights and voucher guardrails for two actions.",
        "Q_AGGREGATE": "Total rental assistance reached $7.35 million with District 9 at $1.8 million.",
        "Q_SQL": "Harbor City scores 87 with Lakeview and Southridge grouped per KPI over 80.",
    }
    if failing:
        answers["Q_SIMPLE_QA"] = "Voucher expansion changed."  # missing keywords
    return answers


@pytest.mark.asyncio
async def test_run_smoke_success(tmp_path: Path, respx_mock: respx.Router) -> None:
    fixtures = ScenarioFixtures.load()
    doc_ids = {
        fixture.spec.alias: f"doc-{fixture.spec.alias.lower()}" for fixture in fixtures.documents()
    }
    _mock_success_flows(
        respx_mock,
        fixtures=fixtures,
        doc_ids=doc_ids,
        prompt_answers=_prompt_answers(),
        conversation_id="conv-test",
    )

    config = SmokeRunConfig(
        auth_base_url="http://auth.test",
        agent_base_url="http://agent.test",
        report_path=tmp_path / "report.json",
        email="ava@example.com",
        username="ava",
        password="secret",
        first_name="Ava",
        last_name="Rivera",
        country_code="USA",
        language="en",
        conversation_provider=StubConversationProvider(),
        stream_capabilities={"cross_doc_reasoning"},
        skip_pillars=False,
    )
    summary = await run_smoke(config)

    assert summary.success is True
    assert summary.prompts
    assert all(result.success for result in summary.prompts)
    assert config.report_path.exists()


@pytest.mark.asyncio
async def test_run_smoke_reports_prompt_failures(tmp_path: Path, respx_mock: respx.Router) -> None:
    fixtures = ScenarioFixtures.load()
    doc_ids = {
        fixture.spec.alias: f"doc-{fixture.spec.alias.lower()}" for fixture in fixtures.documents()
    }
    _mock_success_flows(
        respx_mock,
        fixtures=fixtures,
        doc_ids=doc_ids,
        prompt_answers=_prompt_answers(failing=True),
        conversation_id="conv-test",
    )

    config = SmokeRunConfig(
        auth_base_url="http://auth.test",
        agent_base_url="http://agent.test",
        report_path=tmp_path / "report.json",
        email="ava@example.com",
        username="ava",
        password="secret",
        first_name="Ava",
        last_name="Rivera",
        country_code="USA",
        language="en",
        conversation_provider=StubConversationProvider(),
        stream_capabilities={"cross_doc_reasoning"},
        skip_pillars=True,
    )
    summary = await run_smoke(config)

    assert summary.success is False
    assert any(not result.success for result in summary.prompts)
    assert config.report_path.exists()


@pytest.mark.asyncio
async def test_run_smoke_http_conversation_bootstrap(
    tmp_path: Path, respx_mock: respx.Router
) -> None:
    fixtures = ScenarioFixtures.load()
    doc_ids = {
        fixture.spec.alias: f"doc-{fixture.spec.alias.lower()}" for fixture in fixtures.documents()
    }
    conversation_id = "conv-http"
    conversation_route = respx_mock.post("http://agent.test/v1/conversations").mock(
        return_value=httpx.Response(
            201,
            json={
                "conversation": {
                    "conversation_id": conversation_id,
                    "owner_user_id": "user-123",
                    "namespace": "reduced-e2e",
                    "status": "active",
                    "tags": ["reduced_e2e", "demo"],
                    "created_at": "2025-01-01T00:00:00Z",
                },
                "created": True,
                "request_id": "req-conv",
            },
        )
    )
    _mock_success_flows(
        respx_mock,
        fixtures=fixtures,
        doc_ids=doc_ids,
        prompt_answers=_prompt_answers(),
        conversation_id=conversation_id,
    )

    config = SmokeRunConfig(
        auth_base_url="http://auth.test",
        agent_base_url="http://agent.test",
        report_path=tmp_path / "report.json",
        email="ava@example.com",
        username="ava",
        password="secret",
        first_name="Ava",
        last_name="Rivera",
        country_code="USA",
        language="en",
        stream_capabilities={"cross_doc_reasoning"},
        skip_pillars=False,
    )
    summary = await run_smoke(config)

    assert summary.success is True
    assert conversation_route.called


@pytest.mark.asyncio
async def test_run_smoke_reseed_triggers_demo_endpoints(
    tmp_path: Path, respx_mock: respx.Router
) -> None:
    fixtures = ScenarioFixtures.load()
    doc_ids = {
        fixture.spec.alias: f"doc-{fixture.spec.alias.lower()}" for fixture in fixtures.documents()
    }
    conversation_id = "conv-demo"
    _mock_success_flows(
        respx_mock,
        fixtures=fixtures,
        doc_ids=doc_ids,
        prompt_answers=_prompt_answers(),
        conversation_id=conversation_id,
        include_demo_cleanup=True,
    )

    config = SmokeRunConfig(
        auth_base_url="http://auth.test",
        agent_base_url="http://agent.test",
        report_path=tmp_path / "report.json",
        email="ava@example.com",
        username="ava",
        password="secret",
        first_name="Ava",
        last_name="Rivera",
        country_code="USA",
        language="en",
        reseed_docs=True,
        stream_capabilities={"cross_doc_reasoning"},
    )
    summary = await run_smoke(config)

    assert summary.success is True
    paths = [call.request.url.path for call in respx_mock.calls]
    assert any(path.endswith("/v1/demo/reset-conversation") for path in paths)
    assert any(path.endswith("/v1/demo/purge-documents") for path in paths)


@pytest.mark.asyncio
async def test_run_smoke_cleanup_only_skips_uploads(
    tmp_path: Path, respx_mock: respx.Router
) -> None:
    fixtures = ScenarioFixtures.load()
    conversation_id = "conv-clean"
    doc_ids = {
        fixture.spec.alias: f"doc-{fixture.spec.alias.lower()}" for fixture in fixtures.documents()
    }
    _mock_success_flows(
        respx_mock,
        fixtures=fixtures,
        doc_ids=doc_ids,
        prompt_answers=_prompt_answers(),
        conversation_id=conversation_id,
        include_demo_cleanup=True,
    )

    config = SmokeRunConfig(
        auth_base_url="http://auth.test",
        agent_base_url="http://agent.test",
        report_path=tmp_path / "report.json",
        email="ava@example.com",
        username="ava",
        password="secret",
        first_name="Ava",
        last_name="Rivera",
        country_code="USA",
        language="en",
        stream_capabilities={"cross_doc_reasoning"},
        reseed_docs=True,
        cleanup_only=True,
    )
    summary = await run_smoke(config)

    assert summary.success is True
    assert not summary.prompts
