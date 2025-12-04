from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from scripts.reduced_e2e_smoke.fixtures import ScenarioFixtures
from scripts.reduced_e2e_smoke.judge import JudgeRequest, JudgeVerdict, PromptJudge
from scripts.reduced_e2e_smoke.runner import SmokeRunConfig, run_smoke


class StubPromptJudge(PromptJudge):
    """Deterministic prompt judge used for unit tests."""

    def __init__(self, *, failure_overrides: set[str] | None = None) -> None:
        self.name = "stub_judge"
        self._failure_overrides = failure_overrides or set()
        self._keywords = {
            "Q_SIMPLE_QA": ("five", "32%"),
            "Q_REASON": ("district 9", "ledger"),
            "Q_AGGREGATE": ("7.35", "district 9"),
            "Q_SQL": ("harbor city",),
        }

    async def evaluate(self, request: JudgeRequest) -> JudgeVerdict:
        if request.prompt_id in self._failure_overrides:
            return JudgeVerdict(
                passed=False,
                score=0.05,
                reasons=[f"{request.prompt_id} forced failure"],
            )
        text = request.answer.lower()
        required = self._keywords.get(request.prompt_id, ())
        missing = [word for word in required if word.lower() not in text]
        if missing:
            return JudgeVerdict(
                passed=False,
                score=0.2,
                reasons=[f"missing keywords: {', '.join(missing)}"],
            )
        return JudgeVerdict(passed=True, score=0.95, reasons=["answer grounded"])


@pytest.fixture
def respx_mock():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def _assert_endpoint_subsequence(respx_mock: respx.Router, expected: list[tuple[str, str]]) -> None:
    observed = [(call.request.method, str(call.request.url)) for call in respx_mock.calls]
    last_index = -1
    for method, suffix in expected:
        try:
            index = next(
                i
                for i, (observed_method, url) in enumerate(observed)
                if url.endswith(suffix) and observed_method == method
            )
        except StopIteration as exc:  # pragma: no cover - assertion helper
            raise AssertionError(
                f"Expected {method} call ending with {suffix!r} was not observed"
            ) from exc
        if index <= last_index:
            raise AssertionError(
                f"Call ending with {suffix!r} occurred out of order (index {index} <= {last_index})"
            )
        last_index = index


def _mock_success_flows(
    respx_mock: respx.Router,
    *,
    fixtures: ScenarioFixtures,
    doc_ids: dict[str, str],
    prompt_answers: dict[str, str],
    conversation_id: str,
    include_demo_cleanup: bool = False,
    skip_main_flow: bool = False,
    localstack_url: str | None = None,
    real_mode: bool = False,
) -> None:
    document_fixtures = fixtures.documents()
    verification_headers = (
        {
            "X-Cache-Mode": "standard",
            "X-RateLimit-Policy": "valkey",
            "Viz-Demo-Mode": "standard",
        }
        if real_mode
        else None
    )
    reduced_scope_meta = (
        {
            "enabled": True,
            "use_real_tools": True,
            "text_only_chunks": False,
            "disable_valkey": False,
            "disable_rate_limiting": False,
            "allowed_chunk_types": ["text"],
        }
        if real_mode
        else None
    )
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
            headers=verification_headers,
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
                "reduced_scope": reduced_scope_meta,
            },
            headers=verification_headers,
        )

    respx_mock.get("http://agent.test/v1/documents").mock(side_effect=document_list_handler)

    upload_iter = iter(document_fixtures)

    if not skip_main_flow:

        def upload_handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            fixture = next(upload_iter)
            alias = fixture.spec.alias
            ingestion = None
            if reduced_scope_meta:
                ingestion = {
                    "stage": "activate",
                    "status": "COMPLETED",
                    "started_at": "2025-01-01T00:00:00Z",
                    "completed_at": "2025-01-01T00:00:05Z",
                }
            return httpx.Response(
                201,
                json={
                    "document_id": doc_ids[alias],
                    "content_hash": fixture.content_hash,
                    "status": "COMPLETED",
                    "message": "ok",
                    "reduced_scope": reduced_scope_meta,
                    "ingestion": ingestion,
                },
                headers=verification_headers,
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
                headers = {"content-type": "text/event-stream"}
                if verification_headers:
                    headers.update(verification_headers)
                return httpx.Response(200, content=sse, headers=headers)
            return httpx.Response(
                200,
                json={"done": done_payload, "messages": [{"content": answer}]},
                headers=verification_headers,
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

    if localstack_url:
        respx_mock.get(f"{localstack_url}/_localstack/health").mock(
            return_value=httpx.Response(200, json={"status": "running"})
        )


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
        localstack_url="http://localstack.test",
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
        prompt_judge=StubPromptJudge(),
        localstack_url="http://localstack.test",
        prompt_judge=StubPromptJudge(),
    )
    summary = await run_smoke(config)

    assert summary.success is True
    assert summary.prompts
    assert all(result.success for result in summary.prompts)
    assert config.report_path.exists()
    _assert_endpoint_subsequence(
        respx_mock,
        [
            ("POST", "/v1/conversations"),
            ("POST", "/v1/documents/upload"),
            ("POST", "/v1/conversations/conv-test/attachments"),
            ("POST", "/v1/chat"),
            ("GET", "/v1/conversations/conv-test/pillars"),
            ("GET", "/_localstack/health"),
        ],
    )


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
        stream_capabilities={"cross_doc_reasoning"},
        skip_pillars=True,
        prompt_judge=StubPromptJudge(),
    )
    summary = await run_smoke(config)

    assert summary.success is False
    assert any(not result.success for result in summary.prompts)
    assert config.report_path.exists()


@pytest.mark.asyncio
async def test_run_smoke_real_tools_verification(tmp_path: Path, respx_mock: respx.Router) -> None:
    fixtures = ScenarioFixtures.load()
    doc_ids = {
        fixture.spec.alias: f"doc-{fixture.spec.alias.lower()}" for fixture in fixtures.documents()
    }
    _mock_success_flows(
        respx_mock,
        fixtures=fixtures,
        doc_ids=doc_ids,
        prompt_answers=_prompt_answers(),
        conversation_id="conv-real",
        real_mode=True,
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
        skip_pillars=True,
        use_real_tools=True,
        verify_real_tools=True,
        prompt_judge=StubPromptJudge(),
    )
    summary = await run_smoke(config)

    assert summary.success is True
    real_tools = summary.telemetry.get("real_tools")
    assert real_tools is not None
    assert real_tools["verified"] is True
    assert real_tools["embedding_jobs"] == len(doc_ids)
    assert any(stage.name == "real_tool_preflight" for stage in summary.stages)


@pytest.mark.asyncio
async def test_run_smoke_real_tools_verification_failure(
    tmp_path: Path, respx_mock: respx.Router
) -> None:
    fixtures = ScenarioFixtures.load()
    doc_ids = {
        fixture.spec.alias: f"doc-{fixture.spec.alias.lower()}" for fixture in fixtures.documents()
    }
    _mock_success_flows(
        respx_mock,
        fixtures=fixtures,
        doc_ids=doc_ids,
        prompt_answers=_prompt_answers(),
        conversation_id="conv-real-fail",
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
        skip_pillars=True,
        use_real_tools=True,
        verify_real_tools=True,
        prompt_judge=StubPromptJudge(),
    )
    summary = await run_smoke(config)

    assert summary.success is False
    failure_stage = next(
        stage for stage in summary.stages if stage.name == "real_tool_verification"
    )
    assert failure_stage.success is False


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
        localstack_url="http://localstack.test",
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
        localstack_url="http://localstack.test",
        prompt_judge=StubPromptJudge(),
    )
    summary = await run_smoke(config)

    assert summary.success is True
    _assert_endpoint_subsequence(
        respx_mock,
        [
            ("POST", "/v1/conversations"),
            ("POST", "/v1/demo/reset-conversation"),
            ("POST", "/v1/demo/purge-documents"),
            ("POST", "/v1/documents/upload"),
            ("POST", f"/v1/conversations/{conversation_id}/attachments"),
            ("POST", "/v1/chat"),
            ("GET", f"/v1/conversations/{conversation_id}/pillars"),
            ("GET", "/_localstack/health"),
        ],
    )


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
        skip_main_flow=True,
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
        prompt_judge=StubPromptJudge(),
    )
    summary = await run_smoke(config)

    assert summary.success is True
    assert not summary.prompts
