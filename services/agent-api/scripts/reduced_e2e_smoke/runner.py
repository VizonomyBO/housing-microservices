"""Core orchestration logic for the reduced E2E smoke CLI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from scripts.reduced_e2e_fixtures import DocumentFixture, PromptSpec

from .bootstrap import ConversationBootstrapper, HttpConversationBootstrapper
from .clients import (
    LoginResult,
    UploadResult,
    attach_document,
    chat_blocking,
    chat_streaming,
    fetch_pillars,
    list_attachments,
    list_conversations,
    list_documents,
    login_user,
    probe_localstack,
    purge_demo_documents,
    register_user,
    reset_demo_conversation,
    upload_document,
)
from .errors import SmokeError
from .fixtures import ScenarioFixtures
from .reporting import PromptRunResult, RunSummary, StageResult, render_and_print, write_json_report
from .validators import validate_prompt


@dataclass(slots=True)
class SmokeRunConfig:
    auth_base_url: str
    agent_base_url: str
    report_path: Path
    email: str
    username: str
    password: str
    first_name: str
    last_name: str
    country_code: str
    language: str
    tags: tuple[str, ...] = ("reduced_e2e", "demo")
    timeout_seconds: float = 30.0
    stream_capabilities: set[str] = field(default_factory=lambda: {"cross_doc_reasoning"})
    database_url: str | None = None
    localstack_url: str | None = None
    skip_pillars: bool = False
    conversation_provider: ConversationBootstrapper | None = None
    reseed_docs: bool = False
    cleanup_only: bool = False


async def run_smoke(config: SmokeRunConfig) -> RunSummary:
    fixtures = ScenarioFixtures.load()
    manifest = fixtures.manifest
    started_at = datetime.now(UTC)
    stages: list[StageResult] = []
    prompt_results: list[PromptRunResult] = []

    timeout = httpx.Timeout(config.timeout_seconds)
    async with (
        httpx.AsyncClient(
            base_url=_normalize_url(config.auth_base_url), timeout=timeout
        ) as auth_client,
        httpx.AsyncClient(
            base_url=_normalize_url(config.agent_base_url), timeout=timeout
        ) as agent_client,
    ):
        recorder = _StageRecorder(stages)
        login_result: LoginResult
        conversation_id: str
        uploaded_docs: dict[str, UploadResult] = {}

        try:
            await recorder.record(
                "register", lambda: register_user(auth_client, _register_payload(config))
            )
            login_result = await recorder.record(
                "login",
                lambda: login_user(
                    auth_client, {"login": config.email, "password": config.password}
                ),
                metadata_fn=lambda result: {"user_id": result.user_id},
            )

            provider = config.conversation_provider
            if provider is None:
                provider = HttpConversationBootstrapper(
                    client=agent_client,
                    token=login_result.access_token,
                    namespace="reduced-e2e",
                    tags=config.tags,
                )

            conversation_id = await recorder.record(
                "conversation_bootstrap",
                lambda: provider.ensure_conversation(
                    owner_user_id=login_result.user_id,
                    country_code=config.country_code,
                ),
                metadata_fn=lambda cid: {"conversation_id": cid},
            )

            await recorder.record(
                "conversation_inventory",
                lambda: _fetch_conversation_entry(
                    agent_client,
                    token=login_result.access_token,
                    conversation_id=conversation_id,
                    tags=config.tags,
                    country_code=config.country_code,
                ),
                metadata_fn=lambda entry: {
                    "document_count": entry.get("document_count", 0),
                    "last_activity": entry.get("last_activity_at"),
                },
            )

            cleanup_requested = config.reseed_docs or config.cleanup_only
            if cleanup_requested:
                await recorder.record(
                    "demo_reset_conversation",
                    lambda: reset_demo_conversation(
                        agent_client,
                        login_result.access_token,
                        {"conversation_id": conversation_id},
                    ),
                    metadata_fn=lambda data: {
                        "detached": data.get("detached_documents"),
                        "deleted_messages": data.get("deleted_messages"),
                    },
                )
                if config.reseed_docs:
                    purge_payload = _build_demo_purge_payload(fixtures)
                    await recorder.record(
                        "demo_purge_documents",
                        lambda: purge_demo_documents(
                            agent_client,
                            login_result.access_token,
                            purge_payload,
                        ),
                        metadata_fn=lambda data: {"purged": data.get("purged_documents")},
                    )

                await recorder.record(
                    "verify_conversation_reset",
                    lambda: _verify_conversation_doc_count(
                        agent_client,
                        token=login_result.access_token,
                        conversation_id=conversation_id,
                        tags=config.tags,
                        country_code=config.country_code,
                        minimum=0,
                        exact=True,
                    ),
                    metadata_fn=lambda entry: {"document_count": entry.get("document_count", 0)},
                )

            if not config.cleanup_only:
                uploaded_docs = await recorder.record(
                    "upload_documents",
                    lambda: _upload_all_documents(
                        agent_client,
                        token=login_result.access_token,
                        owner_user_id=login_result.user_id,
                        fixtures=fixtures.documents(),
                        scenario=manifest.scenario,
                        tags=config.tags,
                    ),
                    metadata_fn=lambda result: {"uploaded": len(result)},
                )

                await recorder.record(
                    "document_inventory",
                    lambda: _verify_document_inventory(
                        agent_client,
                        token=login_result.access_token,
                        aliases=list(uploaded_docs.keys()),
                        tags=config.tags,
                        uploaded_docs=uploaded_docs,
                    ),
                    metadata_fn=lambda payload: {"documents": payload.get("count", 0)},
                )

                await recorder.record(
                    "attach_documents",
                    lambda: _attach_documents(
                        agent_client,
                        token=login_result.access_token,
                        conversation_id=conversation_id,
                        uploaded_docs=uploaded_docs,
                    ),
                    metadata_fn=lambda result: {"attached": result.get("attached", 0)},
                )

                await recorder.record(
                    "conversation_documents_synced",
                    lambda: _verify_conversation_doc_count(
                        agent_client,
                        token=login_result.access_token,
                        conversation_id=conversation_id,
                        tags=config.tags,
                        country_code=config.country_code,
                        minimum=len(uploaded_docs),
                        exact=False,
                    ),
                    metadata_fn=lambda entry: {"document_count": entry.get("document_count", 0)},
                )

                prompt_results, prompts_passed = await _record_prompts_stage(
                    recorder,
                    agent_client,
                    token=login_result.access_token,
                    conversation_id=conversation_id,
                    prompts=fixtures.prompts(),
                    fixtures=fixtures,
                    uploaded_docs=uploaded_docs,
                    stream_capabilities=config.stream_capabilities,
                    country_code=config.country_code,
                )
                if not prompts_passed:
                    raise SmokeError(
                        "Prompt validations failed",
                        context={
                            "failed": [
                                result.prompt_id for result in prompt_results if not result.success
                            ]
                        },
                    )

                if not config.skip_pillars:
                    await recorder.record(
                        "pillars",
                        lambda: fetch_pillars(
                            agent_client, login_result.access_token, conversation_id
                        ),
                    )

                if config.localstack_url:
                    localstack_url = _normalize_url(config.localstack_url)
                    await recorder.record(
                        "localstack",
                        lambda: probe_localstack(localstack_url),
                    )

        except SmokeError:
            pass  # failure already captured in stages

    finished_at = datetime.now(UTC)
    summary = RunSummary(
        scenario=manifest.scenario,
        version=manifest.version,
        started_at=started_at,
        finished_at=finished_at,
        stages=stages,
        prompts=prompt_results,
    )
    write_json_report(summary, config.report_path)
    render_and_print(summary)
    return summary


class _StageRecorder:
    def __init__(self, stages: list[StageResult]) -> None:
        self._stages = stages

    async def record(
        self,
        name: str,
        func: Callable[[], Awaitable[Any]],
        *,
        metadata_fn: Callable[[Any], dict[str, Any]] | None = None,
    ) -> Any:
        start = perf_counter()
        try:
            result = await func()
        except SmokeError as exc:
            latency = (perf_counter() - start) * 1000
            self._stages.append(
                StageResult(
                    name=name,
                    success=False,
                    latency_ms=latency,
                    detail=str(exc),
                    metadata=exc.context,
                )
            )
            raise
        latency = (perf_counter() - start) * 1000
        metadata = metadata_fn(result) if metadata_fn else {}
        self._stages.append(
            StageResult(
                name=name,
                success=True,
                latency_ms=latency,
                detail=None,
                metadata=metadata,
            )
        )
        return result


def _register_payload(config: SmokeRunConfig) -> dict[str, Any]:
    return {
        "email": config.email,
        "username": config.username,
        "password": config.password,
        "first_name": config.first_name,
        "last_name": config.last_name,
        "country_code": config.country_code,
        "role": "public",
    }


def _normalize_url(value: str) -> str:
    stripped = value.rstrip("/")
    if stripped.startswith(("http://", "https://")):
        return stripped
    return f"http://{stripped}"


def _build_demo_purge_payload(fixtures: ScenarioFixtures) -> dict[str, Any]:
    aliases = list(fixtures.list_aliases())
    hashes = [fixture.content_hash for fixture in fixtures.documents()]
    return {
        "document_aliases": aliases,
        "content_hashes": hashes,
    }


async def _upload_all_documents(
    client: httpx.AsyncClient,
    *,
    token: str,
    owner_user_id: str,
    fixtures: list[DocumentFixture],
    scenario: str,
    tags: Sequence[str],
) -> dict[str, UploadResult]:
    uploads: dict[str, UploadResult] = {}
    for fixture in fixtures:
        metadata = dict(fixture.spec.metadata)
        metadata.setdefault("scenario", scenario)
        metadata.setdefault("document_alias", fixture.spec.alias)
        payload = {
            "document_name": fixture.spec.canonical_name,
            "content": fixture.content,
            "content_type": "text/markdown",
            "chunk_type": "text",
            "access_scope": fixture.spec.access_scope,
            "country_code": fixture.spec.country_code,
            "language": fixture.spec.language,
            "tags": _merge_tags(tags, fixture.spec.tags),
            "metadata": metadata,
            "owner_user_id": owner_user_id,
        }
        result = await upload_document(client, token, payload, alias=fixture.spec.alias)
        if result.content_hash != fixture.content_hash:
            raise SmokeError(
                "Content hash mismatch",
                context={
                    "alias": fixture.spec.alias,
                    "expected": fixture.content_hash,
                    "actual": result.content_hash,
                },
            )
        uploads[fixture.spec.alias] = result
    return uploads


async def _attach_documents(
    client: httpx.AsyncClient,
    *,
    token: str,
    conversation_id: str,
    uploaded_docs: dict[str, UploadResult],
) -> dict[str, int]:
    aliases = list(uploaded_docs.keys())
    for index, alias in enumerate(aliases):
        upload = uploaded_docs[alias]
        await attach_document(
            client,
            token,
            conversation_id,
            document_id=upload.document_id,
            auto_attach_base_docs=(index == 0),
        )
    attachments = await list_attachments(client, token, conversation_id)
    attached_ids = {entry.get("document_id") for entry in attachments}
    missing = [
        alias for alias, upload in uploaded_docs.items() if upload.document_id not in attached_ids
    ]
    if missing:
        raise SmokeError("Missing attachments", context={"aliases": missing})
    return {"attached": len(attachments)}


async def _record_prompts_stage(
    recorder: _StageRecorder,
    client: httpx.AsyncClient,
    *,
    token: str,
    conversation_id: str,
    prompts: list[PromptSpec],
    fixtures: ScenarioFixtures,
    uploaded_docs: dict[str, UploadResult],
    stream_capabilities: set[str],
    country_code: str,
) -> tuple[list[PromptRunResult], bool]:
    start = perf_counter()
    prompt_results = await _run_prompts(
        client,
        token=token,
        conversation_id=conversation_id,
        prompts=prompts,
        fixtures=fixtures,
        uploaded_docs=uploaded_docs,
        stream_capabilities=stream_capabilities,
        country_code=country_code,
    )
    latency = (perf_counter() - start) * 1000
    success = all(result.success for result in prompt_results)
    detail = None if success else "Prompt validations failed"
    recorder._stages.append(  # pylint: disable=protected-access
        StageResult(
            name="prompt_matrix",
            success=success,
            latency_ms=latency,
            detail=detail,
            metadata={"count": len(prompt_results)},
        )
    )
    return prompt_results, success


async def _run_prompts(
    client: httpx.AsyncClient,
    *,
    token: str,
    conversation_id: str,
    prompts: list[PromptSpec],
    fixtures: ScenarioFixtures,
    uploaded_docs: dict[str, UploadResult],
    stream_capabilities: set[str],
    country_code: str,
) -> list[PromptRunResult]:
    results: list[PromptRunResult] = []
    doc_map = fixtures.document_map()
    for prompt in prompts:
        documents = [doc_map[alias] for alias in prompt.document_aliases]
        try:
            document_ids = [uploaded_docs[alias].document_id for alias in prompt.document_aliases]
        except KeyError as exc:
            raise SmokeError("Document upload missing", context={"alias": str(exc)}) from exc
        mode = "stream" if prompt.capability in stream_capabilities else "blocking"
        payload = _build_chat_payload(
            prompt,
            conversation_id=conversation_id,
            document_ids=document_ids,
            country_code=country_code,
            mode=mode,
        )
        run_start = perf_counter()
        if mode == "stream":
            completion = await chat_streaming(client, token, payload)
        else:
            completion = await chat_blocking(client, token, payload)
        latency = (perf_counter() - run_start) * 1000
        validation = validate_prompt(
            prompt,
            answer_text=completion.answer_text,
            done_payload=completion.done_payload,
            expected_document_ids=document_ids,
            cited_document_ids=completion.cited_document_ids,
            document_fixtures=documents,
        )
        results.append(
            PromptRunResult(
                prompt_id=prompt.id,
                capability=prompt.capability,
                mode=mode,
                success=validation.passed,
                latency_ms=latency,
                failures=validation.failures,
                response_excerpt=completion.answer_text[:240],
            )
        )
    return results


def _build_chat_payload(
    prompt: PromptSpec,
    *,
    conversation_id: str,
    document_ids: list[str],
    country_code: str,
    mode: str,
) -> dict[str, Any]:
    attachments = [
        {
            "type": "document_reference",
            "document_id": document_id,
            "visibility": "visible",
            "role": "primary",
            "attach_source": "reduced_e2e_cli",
        }
        for document_id in document_ids
    ]
    return {
        "thread_id": conversation_id,
        "message": {
            "type": "user",
            "content": prompt.question,
            "attachments": attachments,
        },
        "hints": {
            "expected_traits": prompt.expected_traits,
            "prompt_id": prompt.id,
        },
        "constraints": {
            "country_code": country_code,
            "auto_attach_base_docs": False,
        },
        "response_mode": "stream" if mode == "stream" else "blocking",
    }


def _merge_tags(base: Sequence[str], extra: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in list(base) + list(extra):
        normalized = (value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


async def _fetch_conversation_entry(
    client: httpx.AsyncClient,
    *,
    token: str,
    conversation_id: str,
    tags: Sequence[str],
    country_code: str | None,
) -> dict[str, Any]:
    page = 1
    while page <= 20:
        payload = await list_conversations(
            client,
            token,
            page=page,
            page_size=50,
            tags=tags,
            country_code=country_code,
        )
        conversations = payload.get("conversations") or []
        for entry in conversations:
            if entry.get("conversation_id") == conversation_id:
                return entry
        pagination = payload.get("pagination") or {}
        if not pagination.get("has_next"):
            break
        page += 1
    raise SmokeError(
        "Conversation listing missing expected record",
        context={"conversation_id": conversation_id},
    )


async def _verify_conversation_doc_count(
    client: httpx.AsyncClient,
    *,
    token: str,
    conversation_id: str,
    tags: Sequence[str],
    country_code: str | None,
    minimum: int,
    exact: bool,
) -> dict[str, Any]:
    entry = await _fetch_conversation_entry(
        client,
        token=token,
        conversation_id=conversation_id,
        tags=tags,
        country_code=country_code,
    )
    count = int(entry.get("document_count") or 0)
    if exact and count != minimum:
        raise SmokeError(
            "Unexpected conversation document count",
            context={"expected": minimum, "actual": count},
        )
    if not exact and count < minimum:
        raise SmokeError(
            "Conversation has fewer documents than expected",
            context={"expected_min": minimum, "actual": count},
        )
    return entry


async def _verify_document_inventory(
    client: httpx.AsyncClient,
    *,
    token: str,
    aliases: Sequence[str],
    tags: Sequence[str],
    uploaded_docs: dict[str, UploadResult],
) -> dict[str, Any]:
    page = 1
    alias_map: dict[str, dict[str, Any]] = {}
    while page <= 20:
        payload = await list_documents(
            client,
            token,
            page=page,
            page_size=50,
            tags=tags,
        )
        documents = payload.get("documents") or []
        for entry in documents:
            metadata = entry.get("metadata") or {}
            alias = metadata.get("document_alias")
            if alias:
                alias_map.setdefault(alias, entry)
        pagination = payload.get("pagination") or {}
        if not pagination.get("has_next"):
            break
        page += 1
    missing = [alias for alias in aliases if alias not in alias_map]
    if missing:
        raise SmokeError("Document listing missing aliases", context={"aliases": missing})
    for alias in aliases:
        expected_hash = uploaded_docs[alias].content_hash.lower()
        actual_hash = str(alias_map[alias].get("content_hash") or "").lower()
        if actual_hash != expected_hash:
            raise SmokeError(
                "Document hash mismatch",
                context={"alias": alias, "expected": expected_hash, "actual": actual_hash},
            )
    return {"count": len(aliases)}


__all__ = ["SmokeRunConfig", "run_smoke"]
