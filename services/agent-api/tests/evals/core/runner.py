from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from authlib.jose import jwt

from .judges import JudgeSelector
from .metrics import MetricEngine, MetricResult
from .scenarios import EvalScenario
from .telemetry import EvalTelemetrySink


@dataclass(slots=True)
class EvalResult:
    """Aggregate result for a scenario execution."""

    scenario: EvalScenario
    response: dict[str, Any]
    metrics: list[MetricResult]
    telemetry: EvalTelemetrySink
    latency_ms: float | None = None

    def assert_thresholds(self) -> None:
        failures = [
            result
            for result in self.metrics
            if result.threshold is not None and result.status == "ok" and not result.passed
        ]
        if failures:
            messages = [
                f"{res.name} expected>={res.threshold} scored {res.score}" for res in failures
            ]
            raise AssertionError("; ".join(messages))

    def write_artifacts(self, base_dir: str | Path | None = None) -> Path:
        env_dir = os.getenv("EVAL_ARTIFACTS_DIR")
        if base_dir:
            root = Path(base_dir)
        elif env_dir:
            root = Path(env_dir)
        else:
            artifacts_root = Path(__file__).resolve().parents[1] / "artifacts"
            root = artifacts_root / "evals"
        run_dir = root / f"{int(time.time())}" / self.scenario.name.replace(" ", "_")
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "scenario": self.scenario.model_dump(),
            "response": self.response,
            "metrics": [asdict(result) for result in self.metrics],
            "telemetry": self.telemetry.as_dict(),
            "latency_ms": self.latency_ms,
        }
        output_path = run_dir / "result.json"
        output_path.write_text(json.dumps(payload, indent=2))
        return output_path


class EvalRunner:
    """High-level runner that executes eval scenarios against the real Agent API."""

    def __init__(
        self,
        *,
        judge_selector: JudgeSelector | None = None,
        metric_engine: MetricEngine | None = None,
    ) -> None:
        self.judge_selector = judge_selector or JudgeSelector()
        self.metric_engine = metric_engine or MetricEngine(judge_selector=self.judge_selector)

    def run(self, scenario: EvalScenario, *, use_local_judge: bool = False) -> EvalResult:
        telemetry = EvalTelemetrySink()
        base_url = scenario.run_config.base_url or os.environ.get("AGENT_BASE_URL")
        if not base_url:
            raise RuntimeError("EVAL_BASE_URL or AGENT_BASE_URL is required for eval runs.")
        token = self._mint_token(
            user_id=scenario.run_config.user_id,
            tenant_id=scenario.run_config.tenant_id,
            secret=scenario.run_config.auth_shared_secret,
        )
        headers = {"Authorization": f"Bearer {token}"}

        payload = scenario.to_chat_payload()
        for ref in scenario.doc_refs:
            telemetry.record(chunk_id=ref.document_id, score=1.0)

        with httpx.Client(base_url=base_url, headers=headers, timeout=120) as client:
            conversation_id = self._ensure_conversation(client=client, scenario=scenario)
            self._attach_documents(
                client=client, conversation_id=conversation_id, scenario=scenario
            )
            payload["thread_id"] = conversation_id
            payload["allow_stateless"] = False

            start = time.perf_counter()
            response = client.post("/v1/chat", json=payload)
            latency_ms = (time.perf_counter() - start) * 1000
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - surfaced to pytest
                raise AssertionError(
                    f"chat call failed: {exc.response.status_code} {exc.response.text}"
                ) from exc

        body = response.json()
        answer_text = self._extract_answer(body)
        contexts = scenario.document_contexts()

        metric_results: list[MetricResult] = []
        for expectation in scenario.expectations:
            metric_results.extend(
                self.metric_engine.evaluate(
                    scenario=scenario,
                    response_text=answer_text,
                    expectation=expectation,
                    telemetry=telemetry,
                    latency_ms=latency_ms,
                    specs=scenario.metrics,
                    use_local_judge=use_local_judge,
                    contexts=contexts,
                    question=scenario.turns[-1].content,
                )
            )

        result = EvalResult(
            scenario=scenario,
            response=body,
            metrics=metric_results,
            telemetry=telemetry,
            latency_ms=latency_ms,
        )
        return result

    def _extract_answer(self, response_body: dict[str, Any]) -> str:
        done = response_body.get("done") or {}
        if isinstance(done, dict) and "answer" in done:
            return str(done["answer"])
        messages = response_body.get("messages") or []
        if messages:
            return str(messages[-1].get("content", ""))
        return ""

    def _mint_token(self, *, user_id: str, tenant_id: str | None, secret: str | None) -> str:
        if not secret:
            raise RuntimeError("AUTH_SHARED_SECRET (or EVAL_AUTH_SECRET) is required for eval runs.")
        claims = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "type": "access",
            "scope": "user",
            "iss": "eval-suite",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        return jwt.encode({"alg": "HS256"}, claims, secret).decode()

    def _ensure_conversation(self, *, client: httpx.Client, scenario: EvalScenario) -> str:
        payload = {
            "title": scenario.name,
            "namespace": "eval-suite",
            "tags": scenario.tags or ["eval"],
            "metadata": {"dataset": scenario.dataset},
        }
        response = client.post("/v1/conversations", json=payload)
        response.raise_for_status()
        data = response.json()
        conversation = data.get("conversation") or {}
        conversation_id = conversation.get("conversation_id")
        if not conversation_id:
            raise RuntimeError("Conversation creation did not return an id.")
        return conversation_id

    def _attach_documents(
        self, *, client: httpx.Client, conversation_id: str, scenario: EvalScenario
    ) -> None:
        if not scenario.doc_refs:
            return
        doc_ids = [ref.document_id for ref in scenario.doc_refs]
        payload = {
            "document_ids": doc_ids,
            "visibility": "read_only",
            "role": "reference",
        }
        response = client.post(f"/v1/conversations/{conversation_id}/attachments/bulk", json=payload)
        response.raise_for_status()
