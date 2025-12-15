"""LangGraph node that evaluates HITL pause/resume criteria."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hitl import HumanGateDecision, HumanGateResumeResult, HumanGateService
from state.agent_state import AgentState
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, lifecycle_span


class HumanGateNodeError(RuntimeError):
    """Raised when the HumanGate node cannot proceed."""


@dataclass(slots=True)
class HumanGateNode:
    """Adapter that wires HumanGateService into the LangGraph state machine."""

    service: HumanGateService

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        if not state.conversation_id:
            raise HumanGateNodeError("HumanGate requires conversation_id in AgentState")

        event_emitter = sse_emitter.as_event_emitter() if sse_emitter else None
        async with lifecycle_span(
            emitter=sse_emitter,
            node="human_gate",
            subgraph="control",
            metadata={"phase": "hitl"},
        ):
            decision = await self.service.evaluate(state, event_emitter=event_emitter)
            add_metadata(paused=decision.paused, reason=decision.reason)
            return self._serialize_state_updates(decision)

    async def resume_from_hitl(
        self,
        conversation_id: str,
        resume_token: str,
        *,
        sse_emitter: SSEEmitter | None = None,
    ) -> AgentState:
        """Expose service resume flow so controllers/tests can hydrate paused runs."""

        event_emitter = sse_emitter.as_event_emitter() if sse_emitter else None
        result: HumanGateResumeResult = await self.service.resume_from_hitl(
            conversation_id, resume_token, event_emitter=event_emitter
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
        return updates
