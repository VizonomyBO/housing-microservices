"""AnalystPlanner node implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from state.agent_state import AgentState, AnalystPlan, AnalystPlanStep, WorkflowPlan
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, lifecycle_span


class AnalystPlannerError(RuntimeError):
    """Raised when prerequisites for the analyst planner are missing."""


def _format_preconditions(preconditions: dict[str, Any]) -> list[str]:
    entries: list[str] = []
    for key in sorted(preconditions):
        value = preconditions[key]
        entries.append(f"{key}:{value}")
    return entries


@dataclass(slots=True)
class AnalystPlannerNode:
    """Builds structured analyst plans from workflow graphs."""

    max_summary_chars: int = 240

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        workflow_plan = state.workflow_plan
        if workflow_plan is None:
            raise AnalystPlannerError("AnalystPlanner requires workflow_plan to be present")
        async with lifecycle_span(
            emitter=sse_emitter,
            node="analyst_planner",
            subgraph="analyst",
            metadata={"workflow_version": workflow_plan.version},
        ):
            summary = self._summarize_plan(state, workflow_plan)
            steps = [
                AnalystPlanStep(
                    key=step.key,
                    description=step.description,
                    required_context=_format_preconditions(step.preconditions),
                    expected_outputs=sorted(step.artifacts.keys()),
                    workflow_ref=step.key,
                )
                for step in workflow_plan.steps
            ]
            complexity = self._compute_complexity(steps, workflow_plan)
            plan = AnalystPlan(
                plan_id=workflow_plan.plan_id,
                summary=summary,
                steps=steps,
                complexity_score=complexity,
                metadata={
                    "workflow_version": workflow_plan.version,
                    "prerequisites": workflow_plan.prerequisites,
                },
            )
            metrics = dict(state.subgraph_metrics)
            metrics.update(
                {
                    "analyst.plan.steps": len(steps),
                    "analyst.plan.complexity": complexity,
                }
            )
            add_metadata(step_count=len(steps), complexity=complexity)
            return {
                "analyst_plan": plan,
                "subgraph_metrics": metrics,
            }

    def _summarize_plan(self, state: AgentState, workflow_plan: WorkflowPlan) -> str:
        normalized = state.normalized_input
        base_prompt = normalized.normalized_prompt if normalized else "Analyst request"
        summary = f"Plan for {base_prompt.strip()} ({len(workflow_plan.steps)} steps)"
        if len(summary) > self.max_summary_chars:
            summary = summary[: self.max_summary_chars - 3] + "..."
        return summary

    def _compute_complexity(
        self, steps: list[AnalystPlanStep], workflow_plan: WorkflowPlan
    ) -> float:
        step_score = len(steps) / 10
        prereq_score = len(workflow_plan.prerequisites) / 8 if workflow_plan.prerequisites else 0.0
        complexity = min(1.0, round(step_score + prereq_score, 2))
        return complexity


__all__ = ["AnalystPlannerError", "AnalystPlannerNode"]
