from __future__ import annotations

import json
import pathlib
import time
from typing import List

from .client import AgentApiClient
from .metrics import MetricEvaluator
from .results import EvalResult, MetricResult
from .scenarios import MetricSpec, ResolvedScenario
from .telemetry import ChatResult


class EvalRunner:
    def __init__(
        self,
        client: AgentApiClient,
        metrics: MetricEvaluator,
        artifact_dir: pathlib.Path,
    ) -> None:
        self.client = client
        self.metrics = metrics
        self.artifact_dir = artifact_dir

    def run(self, resolved: ResolvedScenario) -> EvalResult:
        scenario = resolved.scenario
        conversation_id = self.client.create_conversation(
            country_code=scenario.constraints.get("country_code", "USA"),
            namespace=scenario.constraints.get("namespace", "eval"),
            title=scenario.name,
            tags=scenario.tags,
        )
        self.client.attach_documents(
            conversation_id=conversation_id,
            document_ids=[doc.document_id for doc in resolved.documents],
        )

        # Execute the first turn (scenarios in this suite are single-turn by design).
        turn = scenario.turns[0]
        constraints = {**scenario.constraints}
        constraints.setdefault("auto_attach_base_docs", False)
        chat_result = self._send_turn(
            conversation_id=conversation_id,
            message=turn.content,
            constraints=constraints,
            response_mode=turn.response_mode,
        )
        metric_results = self._evaluate_metrics(chat_result, turn.metrics, turn.content, resolved)

        eval_result = EvalResult(
            scenario_name=scenario.name,
            chat_result=chat_result,
            metrics=metric_results,
        )
        self._write_artifact(eval_result, resolved)
        return eval_result

    def _send_turn(
        self,
        conversation_id: str,
        message: str,
        constraints: dict,
        response_mode: str,
    ) -> ChatResult:
        if response_mode == "stream":
            return self.client.chat_stream(
                conversation_id=conversation_id,
                message=message,
                constraints=constraints,
            )
        return self.client.chat_blocking(
            conversation_id=conversation_id,
            message=message,
            constraints=constraints,
            response_mode=response_mode,
        )

    def _evaluate_metrics(
        self,
        chat_result: ChatResult,
        metric_specs: List[MetricSpec],
        question: str,
        resolved: ResolvedScenario,
    ) -> List[MetricResult]:
        return self.metrics.evaluate(
            chat_result=chat_result,
            metric_specs=metric_specs,
            question=question,
            context_docs=resolved.documents,
        )

    def _write_artifact(self, eval_result: EvalResult, resolved: ResolvedScenario) -> None:
        ts = time.strftime("%Y%m%dT%H%M%S")
        scenario_dir = self.artifact_dir / ts / eval_result.scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)
        artifact = {
            "scenario": resolved.scenario.model_dump(),
            "documents": [doc.model_dump() for doc in resolved.documents],
            "chat_result": {
                "answer": eval_result.chat_result.answer,
                "citations": [citation.__dict__ for citation in eval_result.chat_result.citations],
                "response_mode": eval_result.chat_result.response_mode,
                "status_code": eval_result.chat_result.status_code,
                "duration_ms": eval_result.chat_result.duration_ms,
                "request_id": eval_result.chat_result.request_id,
            },
            "metrics": [metric.__dict__ for metric in eval_result.metrics],
        }
        with (scenario_dir / "result.json").open("w", encoding="utf-8") as handle:
            json.dump(artifact, handle, indent=2)
