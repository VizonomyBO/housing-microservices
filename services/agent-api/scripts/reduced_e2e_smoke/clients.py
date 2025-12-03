"""httpx helper functions for the reduced E2E smoke CLI."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from .errors import SmokeError


@dataclass(slots=True)
class RegisterResult:
    created: bool
    payload: dict[str, Any]


@dataclass(slots=True)
class LoginResult:
    user_id: str
    access_token: str
    refresh_token: str
    payload: dict[str, Any]


@dataclass(slots=True)
class UploadResult:
    alias: str
    document_id: str
    content_hash: str
    status: str
    payload: dict[str, Any]


@dataclass(slots=True)
class ConversationResult:
    conversation_id: str
    owner_user_id: str
    namespace: str
    created: bool
    payload: dict[str, Any]


@dataclass(slots=True)
class ChatCompletion:
    mode: str
    answer_text: str
    done_payload: dict[str, Any]
    cited_document_ids: list[str]
    events: list[dict[str, Any]] | None = None


async def list_conversations(
    client: httpx.AsyncClient,
    token: str,
    *,
    page: int = 1,
    page_size: int = 20,
    tags: Sequence[str] | None = None,
    country_code: str | None = None,
) -> dict[str, Any]:
    params: list[tuple[str, Any]] = [("page", page), ("page_size", page_size)]
    if tags:
        for tag in tags:
            params.append(("tags", tag))
    if country_code:
        params.append(("country_code", country_code))
    response = await _request(
        client,
        "GET",
        "/v1/conversations",
        headers=_auth_headers(token),
        params=params,
    )
    if response.status_code != 200:
        raise SmokeError(
            f"Conversation list failed ({response.status_code})",
            context={"response": response.text},
        )
    return response.json()


async def list_documents(
    client: httpx.AsyncClient,
    token: str,
    *,
    page: int = 1,
    page_size: int = 20,
    tags: Sequence[str] | None = None,
    content_hashes: Sequence[str] | None = None,
) -> dict[str, Any]:
    params: list[tuple[str, Any]] = [("page", page), ("page_size", page_size)]
    if tags:
        for tag in tags:
            params.append(("tags", tag))
    if content_hashes:
        for value in content_hashes:
            params.append(("content_hash", value))
    response = await _request(
        client,
        "GET",
        "/v1/documents",
        headers=_auth_headers(token),
        params=params,
    )
    if response.status_code != 200:
        raise SmokeError(
            f"Document list failed ({response.status_code})",
            context={"response": response.text},
        )
    return response.json()


async def register_user(client: httpx.AsyncClient, payload: dict[str, Any]) -> RegisterResult:
    response = await _request(client, "POST", "/v1/auth/register", json=payload)
    if response.status_code not in (201, 409):
        raise SmokeError(
            f"Failed to register user ({response.status_code})",
            context={"response": response.text},
        )
    data = response.json()
    return RegisterResult(created=response.status_code == 201, payload=data)


async def login_user(client: httpx.AsyncClient, payload: dict[str, Any]) -> LoginResult:
    response = await _request(client, "POST", "/v1/auth/login", json=payload)
    if response.status_code != 200:
        raise SmokeError(
            f"Failed to login ({response.status_code})",
            context={"response": response.text},
        )
    data = response.json()
    try:
        user_id = str(data["user"]["id"])
        access_token = str(data["access_token"])
        refresh_token = str(data.get("refresh_token") or "")
    except (KeyError, TypeError) as exc:  # pragma: no cover - defensive guard
        raise SmokeError("Login response missing required fields") from exc
    return LoginResult(
        user_id=user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        payload=data,
    )


async def create_conversation(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
) -> ConversationResult:
    response = await _request(
        client,
        "POST",
        "/v1/conversations",
        json=payload,
        headers=_auth_headers(token),
    )
    if response.status_code not in (200, 201):
        raise SmokeError(
            f"Conversation create failed ({response.status_code})",
            context={"response": response.text},
        )
    data = response.json()
    conversation = data.get("conversation") or {}
    conversation_id = conversation.get("conversation_id")
    owner_user_id = conversation.get("owner_user_id")
    namespace = conversation.get("namespace") or payload.get("namespace") or "reduced-e2e"
    if not conversation_id:
        raise SmokeError("Conversation response missing conversation_id")
    if not owner_user_id:
        raise SmokeError("Conversation response missing owner_user_id")
    return ConversationResult(
        conversation_id=str(conversation_id),
        owner_user_id=str(owner_user_id),
        namespace=str(namespace),
        created=bool(data.get("created")),
        payload=data,
    )


async def fetch_conversation(
    client: httpx.AsyncClient,
    token: str,
    conversation_id: str,
) -> ConversationResult:
    response = await _request(
        client,
        "GET",
        f"/v1/conversations/{conversation_id}",
        headers=_auth_headers(token),
    )
    if response.status_code != 200:
        raise SmokeError(
            f"Conversation fetch failed ({response.status_code})",
            context={"conversation_id": conversation_id, "response": response.text},
        )
    data = response.json()
    conversation = data.get("conversation") or {}
    conv_id = conversation.get("conversation_id") or conversation_id
    owner_user_id = conversation.get("owner_user_id")
    namespace = conversation.get("namespace") or "reduced-e2e"
    if not owner_user_id:
        raise SmokeError("Conversation fetch did not include owner_user_id")
    return ConversationResult(
        conversation_id=str(conv_id),
        owner_user_id=str(owner_user_id),
        namespace=str(namespace),
        created=bool(data.get("created") or False),
        payload=data,
    )


async def upload_document(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
    *,
    alias: str,
) -> UploadResult:
    response = await _request(
        client,
        "POST",
        "/v1/documents/upload",
        json=payload,
        headers=_auth_headers(token),
    )
    if response.status_code not in (200, 201, 202):
        raise SmokeError(
            f"Document upload failed ({response.status_code})",
            context={"response": response.text, "alias": alias},
        )
    data = response.json()
    document_id = data.get("document_id")
    if not document_id:
        raise SmokeError("Upload response missing document_id", context={"alias": alias})
    return UploadResult(
        alias=alias,
        document_id=str(document_id),
        content_hash=str(data.get("content_hash")),
        status=str(data.get("status")),
        payload=data,
    )


async def attach_document(
    client: httpx.AsyncClient,
    token: str,
    conversation_id: str,
    *,
    document_id: str,
    auto_attach_base_docs: bool = False,
) -> dict[str, Any]:
    response = await _request(
        client,
        "POST",
        f"/v1/conversations/{conversation_id}/attachments",
        json={
            "document_id": document_id,
            "role": "primary",
            "visibility": "visible",
            "auto_attach_base_docs": auto_attach_base_docs,
        },
        headers=_auth_headers(token),
    )
    if response.status_code not in (201, 202):
        raise SmokeError(
            f"Attachment failed ({response.status_code})",
            context={"conversation_id": conversation_id, "document_id": document_id},
        )
    return response.json()


async def list_attachments(
    client: httpx.AsyncClient,
    token: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    response = await _request(
        client,
        "GET",
        f"/v1/conversations/{conversation_id}/attachments",
        headers=_auth_headers(token),
    )
    if response.status_code != 200:
        raise SmokeError(
            f"Failed to list attachments ({response.status_code})",
            context={"conversation_id": conversation_id},
        )
    data = response.json()
    return list(data.get("attachments") or [])


async def chat_blocking(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
) -> ChatCompletion:
    response = await _request(
        client,
        "POST",
        "/v1/chat",
        json=payload,
        headers=_auth_headers(token),
    )
    if response.status_code != 200:
        raise SmokeError(
            f"Chat request failed ({response.status_code})",
            context={"response": response.text},
        )
    data = response.json()
    done_payload = data.get("done") or {}
    answer_text = _extract_answer(done_payload, data)
    cited_docs = _extract_citations(done_payload)
    return ChatCompletion(
        mode="blocking",
        answer_text=answer_text,
        done_payload=done_payload,
        cited_document_ids=cited_docs,
        events=None,
    )


async def chat_streaming(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
) -> ChatCompletion:
    headers = _auth_headers(token)
    headers["Accept"] = "text/event-stream"
    async with client.stream("POST", "/v1/chat", json=payload, headers=headers) as response:
        if response.status_code >= 400:
            body = await response.aread()
            raise SmokeError(
                f"Streaming chat failed ({response.status_code})",
                context={"response": body.decode("utf-8", "ignore")},
            )
        raw_events = await _collect_sse_events(response)
    normalized_events = _normalize_sse_events(raw_events)
    _ensure_no_stream_errors(normalized_events)
    done_payload = _extract_done_payload(normalized_events)
    answer_text = _extract_answer(done_payload)
    cited_docs = _extract_citations(done_payload)
    return ChatCompletion(
        mode="stream",
        answer_text=answer_text,
        done_payload=done_payload,
        cited_document_ids=cited_docs,
        events=normalized_events,
    )


async def fetch_pillars(
    client: httpx.AsyncClient,
    token: str,
    conversation_id: str,
) -> dict[str, Any]:
    response = await _request(
        client,
        "GET",
        f"/v1/conversations/{conversation_id}/pillars",
        headers=_auth_headers(token),
    )
    if response.status_code != 200:
        raise SmokeError(
            f"Pillar fetch failed ({response.status_code})",
            context={"conversation_id": conversation_id},
        )
    return response.json()


async def reset_demo_conversation(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = await _request(
        client,
        "POST",
        "/v1/demo/reset-conversation",
        json=payload,
        headers=_auth_headers(token),
    )
    if response.status_code != 200:
        raise SmokeError(
            f"Demo conversation reset failed ({response.status_code})",
            context={"response": response.text},
        )
    return response.json()


async def purge_demo_documents(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = await _request(
        client,
        "POST",
        "/v1/demo/purge-documents",
        json=payload,
        headers=_auth_headers(token),
    )
    if response.status_code != 200:
        raise SmokeError(
            f"Demo document purge failed ({response.status_code})",
            context={"response": response.text},
        )
    return response.json()


async def probe_localstack(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=url, timeout=10.0) as client:
        response = await _request(client, "GET", "/_localstack/health")
        if response.status_code != 200:
            raise SmokeError(
                f"LocalStack health check failed ({response.status_code})",
                context={"response": response.text},
            )
        return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def _request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | list[tuple[str, Any]] | None = None,
) -> httpx.Response:
    try:
        response = await client.request(method, url, json=json, headers=headers, params=params)
    except httpx.HTTPError as exc:
        raise SmokeError(f"HTTP error calling {url}: {exc}") from exc
    return response


def _extract_answer(done_payload: dict[str, Any], fallback: dict[str, Any] | None = None) -> str:
    if not done_payload:
        done_payload = {}
    answer = done_payload.get("answer") or done_payload.get("text")
    if answer:
        return str(answer)
    messages = fallback.get("messages") if fallback else None
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict) and "content" in last:
            return str(last.get("content") or "")
    return json.dumps(done_payload)


def _extract_citations(done_payload: dict[str, Any]) -> list[str]:
    citations = done_payload.get("citations") or []
    results: list[str] = []
    if isinstance(citations, list):
        for entry in citations:
            if isinstance(entry, dict):
                doc_id = entry.get("document_id") or entry.get("doc_id")
                if doc_id:
                    results.append(str(doc_id))
    return results


async def _collect_sse_events(response: httpx.Response) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_event: dict[str, Any] | None = None
    async for raw_line in response.aiter_lines():
        if raw_line is None:
            continue
        line = raw_line.strip()
        if not line:
            if current_event:
                events.append(current_event)
                current_event = None
            continue
        if line.startswith("event:"):
            if current_event:
                events.append(current_event)
            current_event = {"event": line.split(":", 1)[1].strip()}
        elif line.startswith("data:"):
            data_line = line.split(":", 1)[1].strip()
            if not current_event:
                current_event = {}
            payload_text = current_event.setdefault("data", [])
            if isinstance(payload_text, list):
                payload_text.append(data_line)
    if current_event:
        events.append(current_event)
    return events


def _normalize_sse_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in events:
        data_lines = event.get("data")
        if isinstance(data_lines, list):
            serialized = "\n".join(data_lines)
            try:
                data_payload = json.loads(serialized)
            except json.JSONDecodeError:
                data_payload = {"raw": serialized}
            normalized.append({"event": event.get("event"), "data": data_payload})
        else:
            normalized.append(event)
    return normalized


def _ensure_no_stream_errors(events: list[dict[str, Any]]) -> None:
    for event in events:
        if event.get("event") == "task_error":
            raise SmokeError("Streaming run emitted task_error", context={"event": event})


def _extract_done_payload(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in events:
        if event.get("event") == "done":
            return event.get("data") or {}
    raise SmokeError("Streaming response missing done event")


__all__ = [
    "ChatCompletion",
    "ConversationResult",
    "LoginResult",
    "RegisterResult",
    "UploadResult",
    "attach_document",
    "chat_blocking",
    "chat_streaming",
    "create_conversation",
    "fetch_conversation",
    "fetch_pillars",
    "list_attachments",
    "list_conversations",
    "list_documents",
    "login_user",
    "probe_localstack",
    "purge_demo_documents",
    "register_user",
    "reset_demo_conversation",
    "upload_document",
]
