"""Router node that runs guardrails then classifies the request."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from guardrails import GuardrailContext, GuardrailEngine, RouteDecision, RouterRoute
from models.retrieval import NormalizedInput
from state.agent_state import AgentState
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, emit_demo_mode_event, lifecycle_span, set_route
from telemetry import get_metrics_registry


class RouterNodeError(RuntimeError):
    """Raised when the router cannot proceed due to missing prerequisites."""


ROUTE_TO_SUBGRAPH = {
    RouterRoute.INFORMATIONAL: "informational_subgraph",
    RouterRoute.ANALYST: "analyst_subgraph",
    RouterRoute.NUMERICAL: "numerical_subgraph",
    RouterRoute.VISION: "vision_subgraph",
    RouterRoute.ESCALATE: "human_gate",
}

NUMERICAL_KEYWORDS = {
    "calculate",
    "table",
    "tables",
    "sql",
    "dataset",
    "data set",
    "chart",
    "average",
    "median",
    "kpi",
    "score",
    "utilization",
    "percentage",
    "percent",
    "threshold",
    "exceed",
    "arrears",
    "guardrail",
    "dashboard",
}
ANALYST_KEYWORDS = {
    "plan",
    "strategy",
    "roadmap",
    "trade-off",
    "risk",
    "compare",
    "recommend",
}
VISION_KEYWORDS = {
    "image",
    "photo",
    "picture",
    "diagram",
    "screenshot",
}


@dataclass(slots=True)
class RouterNode:
    """LangGraph node responsible for guardrails + route classification."""

    guardrail_engine: GuardrailEngine = field(default_factory=GuardrailEngine)
    default_confidence: float = 0.6
    hint_confidence: float = 0.9
    strong_signal_confidence: float = 0.75

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:  # pragma: no cover - exercised via tests
        normalized_input = state.normalized_input
        if normalized_input is None:
            raise RouterNodeError("Router requires normalized_input in AgentState")

        metadata = {
            "node": "router",
            "normalized_scope": getattr(normalized_input, "scope_hash", None),
        }
        guardrail_result = self.guardrail_engine.evaluate(
            GuardrailContext(
                normalized_input=normalized_input, attachment_scope=state.attachment_scope
            )
        )
        for violation in guardrail_result.violations:
            severity = getattr(violation.severity, "value", str(violation.severity))
            _METRICS.record_guardrail_violation(code=violation.code, severity=str(severity))
        async with lifecycle_span(
            emitter=sse_emitter,
            node="router",
            subgraph="control",
            metadata=metadata,
            route=state.route.value if state.route else None,
        ):
            add_metadata(
                guardrails_passed=guardrail_result.passed,
                guardrail_violation_count=len(guardrail_result.violations),
            )

            if not guardrail_result.passed:
                decision = RouteDecision(
                    route=RouterRoute.ESCALATE,
                    confidence=0.0,
                    next_subgraph=ROUTE_TO_SUBGRAPH[RouterRoute.ESCALATE],
                    reason="guardrail_violation",
                )
            else:
                decision = self._classify(state, normalized_input)
                decision = await self._apply_reduced_scope_guard(
                    state=state,
                    decision=decision,
                    sse_emitter=sse_emitter,
                )

            set_route(decision.route)
            add_metadata(
                router_reason=decision.reason,
                route_confidence=decision.confidence,
                next_subgraph=decision.next_subgraph,
            )

            return {
                "route": decision.route,
                "route_confidence": decision.confidence,
                "next_subgraph": decision.next_subgraph,
                "router_reason": decision.reason,
                "guardrail_findings": guardrail_result.violations,
                "guardrails_passed": guardrail_result.passed,
                "cache_metadata": state.cache_metadata,
            }

    def _classify(self, state: AgentState, normalized_input: NormalizedInput) -> RouteDecision:
        prompt = normalized_input.normalized_prompt.lower()
        intent_route = self._extract_intent_route(normalized_input.intent_tags)
        if intent_route:
            return RouteDecision(
                route=intent_route,
                confidence=self.hint_confidence,
                next_subgraph=ROUTE_TO_SUBGRAPH[intent_route],
                reason="hint",
            )

        workflow_hints = self._collect_workflow_hints(state)
        numerical_score = self._score_prompt(prompt, NUMERICAL_KEYWORDS)
        analyst_score = self._score_prompt(prompt, ANALYST_KEYWORDS)
        vision_score = self._score_prompt(prompt, VISION_KEYWORDS)
        digit_density = len(re.findall(r"\d", prompt))
        numerical_score += self._numerical_context_boost(prompt, digit_density)
        table_cues = self._contains_table_cues(prompt)

        if "vision" in workflow_hints or vision_score:
            return RouteDecision(
                route=RouterRoute.VISION,
                confidence=self._confidence_from_score(
                    vision_score, workflow_hit="vision" in workflow_hints
                ),
                next_subgraph=ROUTE_TO_SUBGRAPH[RouterRoute.VISION],
                reason="vision_signal",
            )

        numerical_hint = (
            "polars" in workflow_hints
            or "sql" in workflow_hints
            or table_cues
            or digit_density >= 4
        )

        if numerical_hint or numerical_score >= 2:
            return RouteDecision(
                route=RouterRoute.NUMERICAL,
                confidence=self._confidence_from_score(
                    numerical_score + (1 if numerical_hint else 0), workflow_hit=True
                ),
                next_subgraph=ROUTE_TO_SUBGRAPH[RouterRoute.NUMERICAL],
                reason="numerical_signal",
            )

        if "analyst" in workflow_hints or analyst_score >= 2:
            return RouteDecision(
                route=RouterRoute.ANALYST,
                confidence=self._confidence_from_score(
                    analyst_score, workflow_hit="analyst" in workflow_hints
                ),
                next_subgraph=ROUTE_TO_SUBGRAPH[RouterRoute.ANALYST],
                reason="analyst_signal",
            )

        if analyst_score == 1 or numerical_score == 1:
            route = RouterRoute.ANALYST if analyst_score == 1 else RouterRoute.NUMERICAL
            return RouteDecision(
                route=route,
                confidence=self.default_confidence,
                next_subgraph=ROUTE_TO_SUBGRAPH[route],
                reason="single_keyword",
            )

        return RouteDecision(
            route=RouterRoute.INFORMATIONAL,
            confidence=self.default_confidence,
            next_subgraph=ROUTE_TO_SUBGRAPH[RouterRoute.INFORMATIONAL],
            reason="default",
        )

    async def _apply_reduced_scope_guard(
        self,
        *,
        state: AgentState,
        decision: RouteDecision,
        sse_emitter: SSEEmitter | None,
    ) -> RouteDecision:
        flags = state.reduced_scope_flags
        if not flags.enabled:
            return decision
        route = decision.route
        if route not in {RouterRoute.NUMERICAL, RouterRoute.VISION}:
            return decision
        if not flags.should_skip_capability(route.value):
            return decision
        add_metadata(reduced_scope_skip=route.value)
        if sse_emitter is not None and flags.emit_demo_events:
            await emit_demo_mode_event(
                sse_emitter,
                capability=route.value,
                metadata={"node": "router"},
            )
        return RouteDecision(
            route=RouterRoute.INFORMATIONAL,
            confidence=self.default_confidence,
            next_subgraph=ROUTE_TO_SUBGRAPH[RouterRoute.INFORMATIONAL],
            reason="reduced_scope",
        )

    def _extract_intent_route(self, intent_tags: Iterable[str]) -> RouterRoute | None:
        for tag in intent_tags:
            if not tag.startswith("route:"):
                continue
            candidate = tag.split(":", 1)[1]
            with contextlib.suppress(ValueError):
                return RouterRoute(candidate)
        return None

    def _collect_workflow_hints(self, state: AgentState) -> set[str]:
        hints: set[str] = set()
        if state.workflow_plan:
            for step in state.workflow_plan.steps:
                for tool_hint in step.tool_hints:
                    hints.add(tool_hint.lower())
                if step.key.startswith("vision"):
                    hints.add("vision")
                if step.key.startswith("analyst"):
                    hints.add("analyst")
        return hints

    def _score_prompt(self, prompt: str, keywords: set[str]) -> int:
        return sum(1 for keyword in keywords if keyword in prompt)

    def _numerical_context_boost(self, prompt: str, digit_density: int) -> int:
        boost = 0
        if "kpi" in prompt or "utilization" in prompt or "score" in prompt:
            boost += 1
        if "dashboard" in prompt or "table" in prompt or "| value" in prompt:
            boost += 1
        if digit_density >= 2 and ("percent" in prompt or "%" in prompt or "threshold" in prompt):
            boost += 1
        if "guardrail" in prompt and ("plan" in prompt or "policy" in prompt):
            boost += 1
        return boost

    def _contains_table_cues(self, prompt: str) -> bool:
        if "|" in prompt and (" kpi " in prompt or "| value" in prompt):
            return True
        if "table" in prompt and ("kpi" in prompt or "score" in prompt):
            return True
        return "dashboard" in prompt and ("kpi" in prompt or "utilization" in prompt)

    def _confidence_from_score(self, score: int, workflow_hit: bool = False) -> float:
        if workflow_hit and score >= 2:
            return self.hint_confidence
        if workflow_hit or score >= 2:
            return self.strong_signal_confidence
        return self.default_confidence


_METRICS = get_metrics_registry()
