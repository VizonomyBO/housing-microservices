from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx

from .telemetry import ChatResult, parse_sse_stream, parse_standard_response


@dataclass
class AuthTokens:
    access_token: str
    refresh_token: Optional[str]
    user_id: Optional[str]


class AgentApiClient:
    def __init__(
        self,
        agent_base_url: str,
        auth_base_url: str,
        timeout: float = 60.0,
    ) -> None:
        self.agent_base_url = agent_base_url.rstrip("/")
        self.auth_base_url = auth_base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)
        self._tokens: Optional[AuthTokens] = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AgentApiClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[override]
        self.close()

    def login(self, email: str, password: str) -> AuthTokens:
        resp = self._client.post(
            f"{self.auth_base_url}/v1/auth/login",
            json={"login": email, "password": password},
        )
        resp.raise_for_status()
        payload = resp.json()
        user = payload.get("user") or {}
        tokens = AuthTokens(
            access_token=payload.get("access_token"),
            refresh_token=payload.get("refresh_token"),
            user_id=user.get("user_id") or user.get("id"),
        )
        self._tokens = tokens
        return tokens

    def _headers(self) -> Dict[str, str]:
        if not self._tokens:
            msg = "login must be called before using the AgentApiClient"
            raise RuntimeError(msg)
        return {"Authorization": f"Bearer {self._tokens.access_token}"}

    def list_documents(self, page_size: int = 100) -> Dict[str, Any]:
        resp = self._client.get(
            f"{self.agent_base_url}/v1/documents",
            params={"page": 1, "page_size": page_size},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def create_conversation(
        self,
        country_code: str,
        namespace: str,
        title: str,
        tags: Optional[List[str]] = None,
    ) -> str:
        payload = {
            "country_code": country_code,
            "namespace": namespace,
            "title": title,
            "tags": tags or [],
        }
        resp = self._client.post(
            f"{self.agent_base_url}/v1/conversations",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        conversation = body.get("conversation") or body
        conversation_id = (
            conversation.get("conversation_id")
            or conversation.get("id")
            or conversation.get("thread_id")
        )
        if not conversation_id:
            msg = f"Conversation creation succeeded but no id in response: {body}"
            raise RuntimeError(msg)
        return conversation_id

    def attach_documents(
        self,
        conversation_id: str,
        document_ids: Iterable[str],
        visibility: str = "visible",
        role: str = "primary",
    ) -> Dict[str, Any]:
        payload = {
            "document_ids": list(document_ids),
            "visibility": visibility,
            "role": role,
        }
        resp = self._client.post(
            f"{self.agent_base_url}/v1/conversations/{conversation_id}/attachments/bulk",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def chat_blocking(
        self,
        conversation_id: str,
        message: str,
        constraints: Dict[str, Any],
        response_mode: str = "blocking",
    ) -> ChatResult:
        start = time.monotonic()
        resp = self._client.post(
            f"{self.agent_base_url}/v1/chat",
            json={
                "thread_id": conversation_id,
                "message": {"type": "user", "content": message},
                "constraints": constraints,
                "response_mode": response_mode,
            },
            headers=self._headers(),
        )
        duration_ms = (time.monotonic() - start) * 1000
        resp.raise_for_status()
        payload = resp.json()
        return parse_standard_response(
            payload=payload,
            status_code=resp.status_code,
            response_mode=response_mode,
            duration_ms=duration_ms,
        )

    def chat_stream(
        self,
        conversation_id: str,
        message: str,
        constraints: Dict[str, Any],
    ) -> ChatResult:
        start = time.monotonic()
        with self._client.stream(
            "POST",
            f"{self.agent_base_url}/v1/chat",
            json={
                "thread_id": conversation_id,
                "message": {"type": "user", "content": message},
                "constraints": constraints,
                "response_mode": "stream",
            },
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            result = parse_sse_stream(
                status_code=resp.status_code,
                response_mode="stream",
                lines=resp.iter_lines(),
                duration_ms=0.0,
            )
        result.duration_ms = (time.monotonic() - start) * 1000
        return result
