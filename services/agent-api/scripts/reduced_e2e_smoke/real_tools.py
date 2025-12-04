"""Telemetry + verification helpers for real-tool smoke runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import httpx

from .errors import SmokeError

REAL_HEADER_KEYS = {"x-cache-mode", "viz-demo-mode", "x-ratelimit-policy", "viz-request-id"}


@dataclass(slots=True)
class HttpCallRecord:
    method: str
    host: str
    path: str
    status_code: int
    latency_ms: float | None
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "host": self.host,
            "path": self.path,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "headers": dict(self.headers),
        }


class HttpTelemetryRecorder:
    """Captures per-request latency + header snippets via httpx event hooks."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._calls: list[HttpCallRecord] = []

    def build_event_hooks(self) -> dict[str, list[Callable]]:
        if not self.enabled:
            return {}
        return {
            "request": [self._on_request],
            "response": [self._on_response],
        }

    async def _on_request(self, request: httpx.Request) -> None:
        if not self.enabled:
            return
        request.extensions["real_tools_start"] = perf_counter()

    async def _on_response(self, response: httpx.Response) -> None:
        if not self.enabled:
            return
        request = response.request
        start = request.extensions.pop("real_tools_start", None)
        latency_ms = ((perf_counter() - start) * 1000) if start else None
        path = (
            request.url.raw_path.decode("utf-8", "ignore")
            if request.url.raw_path
            else request.url.path
        )
        record = HttpCallRecord(
            method=request.method,
            host=request.url.host or "",
            path=path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            headers=_filter_headers(response.headers),
        )
        self._calls.append(record)

    def summary(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "total_calls": 0}
        if not self._calls:
            return {"enabled": True, "total_calls": 0}
        total_latency = sum(call.latency_ms or 0.0 for call in self._calls)
        avg_latency = total_latency / len(self._calls) if self._calls else 0.0
        by_path: dict[str, dict[str, Any]] = {}
        for call in self._calls:
            entry = by_path.setdefault(call.path, {"count": 0, "latency_sum": 0.0})
            entry["count"] += 1
            entry["latency_sum"] += call.latency_ms or 0.0
        for value in by_path.values():
            latency_sum = value.pop("latency_sum")
            value["avg_latency_ms"] = latency_sum / value["count"] if value["count"] else 0.0
        samples = [call.to_dict() for call in self._calls[:10]]
        return {
            "enabled": True,
            "total_calls": len(self._calls),
            "avg_latency_ms": avg_latency,
            "paths": by_path,
            "samples": samples,
        }


@dataclass(slots=True)
class RealToolSignal:
    source: str
    headers: dict[str, str]
    reduced_scope: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "headers": dict(self.headers),
            "verified": self.verified,
        }
        if self.reduced_scope is not None:
            payload["reduced_scope"] = dict(self.reduced_scope)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class RealToolVerifier:
    """Aggregates response metadata proving that real-tool mode is active."""

    def __init__(self, *, enabled: bool, require_verification: bool) -> None:
        self.enabled = enabled
        self.require_verification = require_verification
        self.signals: list[RealToolSignal] = []
        self.embedding_jobs: int = 0
        self.reranker_prompts: int = 0

    def record_upload(self, headers: Mapping[str, str], payload: Mapping[str, Any]) -> None:
        if not self.enabled:
            return
        reduced_scope = _coerce_mapping(payload.get("reduced_scope"))
        self._record_signal(
            source="documents.upload",
            headers=headers,
            reduced_scope=reduced_scope,
            metadata={"status": payload.get("status"), "ingestion": payload.get("ingestion")},
        )
        if payload.get("ingestion"):
            self.embedding_jobs += 1

    def record_document_inventory(
        self, headers: Mapping[str, str], payload: Mapping[str, Any]
    ) -> None:
        if not self.enabled:
            return
        reduced_scope = _coerce_mapping(payload.get("reduced_scope"))
        count = len(payload.get("documents") or [])
        self._record_signal(
            source="documents.list",
            headers=headers,
            reduced_scope=reduced_scope,
            metadata={"document_count": count},
        )

    def record_chat(
        self, prompt_id: str, headers: Mapping[str, str], done_payload: Mapping[str, Any]
    ) -> None:
        if not self.enabled:
            return
        metadata = {"prompt_id": prompt_id, "route": done_payload.get("route")}
        citations = done_payload.get("citations")
        if isinstance(citations, list):
            metadata["citations"] = citations
        scope = _coerce_mapping(done_payload.get("reduced_scope"))
        self._record_signal(
            source="chat",
            headers=headers,
            reduced_scope=scope,
            metadata=metadata,
        )

    def record_prompt_capability(self, capability: str, document_aliases: list[str]) -> None:
        if not self.enabled:
            return
        if (
            capability.lower() in {"cross_doc_reasoning", "rerank", "fusion"}
            or len(document_aliases) > 1
        ):
            self.reranker_prompts += 1

    def _record_signal(
        self,
        *,
        source: str,
        headers: Mapping[str, str],
        reduced_scope: Mapping[str, Any] | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RealToolSignal:
        filtered_headers = _filter_headers(headers)
        signal = RealToolSignal(
            source=source,
            headers=filtered_headers,
            reduced_scope=dict(reduced_scope) if reduced_scope else None,
            metadata=dict(metadata) if metadata else {},
        )
        signal.verified = self._is_real_signal(signal)
        self.signals.append(signal)
        return signal

    def _is_real_signal(self, signal: RealToolSignal) -> bool:
        headers = {key.lower(): value.lower() for key, value in signal.headers.items()}
        reduced = signal.reduced_scope or {}
        checks = [
            headers.get("x-cache-mode") == "standard",
            headers.get("x-ratelimit-policy") == "valkey",
            headers.get("viz-demo-mode") == "standard",
            bool(reduced.get("use_real_tools")),
            reduced.get("text_only_chunks") is False,
        ]
        return any(checks)

    def verify(self) -> dict[str, Any]:
        verified = any(signal.verified for signal in self.signals) if self.enabled else False
        if not self.enabled:
            return {
                "requested": False,
                "verified": False,
                "signals_recorded": len(self.signals),
                "embedding_jobs": 0,
                "reranker_prompts": 0,
            }
        if self.require_verification and not verified:
            raise SmokeError(
                "Real tooling verification failed",
                context={
                    "signals": [signal.to_dict() for signal in self.signals],
                    "hint": "Enable --verify-real-tools only when the backend runs with REDUCED_SCOPE_USE_REAL_TOOLS=1",
                },
            )
        return {
            "requested": True,
            "verified": verified,
            "signals_recorded": len(self.signals),
            "embedding_jobs": self.embedding_jobs,
            "reranker_prompts": self.reranker_prompts,
        }


def _filter_headers(headers: Mapping[str, str]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in REAL_HEADER_KEYS:
            filtered[key] = value
    return filtered


def _coerce_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


__all__ = [
    "HttpTelemetryRecorder",
    "RealToolVerifier",
]
