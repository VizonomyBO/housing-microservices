"""LangGraph node that evaluates HITL pause/resume criteria."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hitl import HumanGateDecision, HumanGateResumeResult, HumanGateService
from state.agent_state import AgentState


class HumanGateNodeError(RuntimeError):
    """Raised when the HumanGate node cannot proceed."""


@dataclass(slots=True)
class HumanGateNode:
    """Adapter that wires HumanGateService into the LangGraph state machine."""

    service: HumanGateService

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        if not state.conversation_id:
            raise HumanGateNodeError("HumanGate requires conversation_id in AgentState")

        decision = await self.service.evaluate(state)
        return self._serialize_state_updates(decision)

    async def resume_from_hitl(self, conversation_id: str, resume_token: str) -> AgentState:
        """Expose service resume flow so controllers/tests can hydrate paused runs."""

        result: HumanGateResumeResult = await self.service.resume_from_hitl(
            conversation_id, resume_token
        )
        return result.state

    def _serialize_state_updates(self, decision: HumanGateDecision) -> dict[str, Any]:
        updates: dict[str, Any] = {
            "interrupt_reason": decision.state.interrupt_reason,
            "hitl_transcript": decision.state.hitl_transcript,
        }
        if decision.paused:
            updates.update(
                {
                    "checkpoint_id": decision.state.checkpoint_id,
                    "resume_token": decision.resume_token,
                }
            )
        # TODO(Task 12): forward decision.payload to SSE emitter once streaming hooks land.
        return updates
