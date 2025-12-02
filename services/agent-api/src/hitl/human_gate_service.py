"""Domain service encapsulating HumanGate pause/resume logic."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from guardrails.models import GuardrailSeverity, GuardrailViolation, RouterRoute
from repositories.agent_checkpoint_repository import HydratedCheckpoint
from services.checkpoint_service import CheckpointService
from state.agent_state import AgentState, HitlTranscriptEntry

EventEmitter = Callable[[str, Mapping[str, Any]], Awaitable[None]]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


_DEFAULT_THRESHOLDS: Mapping[RouterRoute, float] = {
    RouterRoute.INFORMATIONAL: 0.55,
    RouterRoute.ANALYST: 0.65,
    RouterRoute.NUMERICAL: 0.7,
    RouterRoute.VISION: 0.6,
    RouterRoute.ESCALATE: 1.0,
}


@dataclass(slots=True)
class HumanGateDecision:
    """Return value describing whether the state was paused for HITL."""

    paused: bool
    state: AgentState
    reason: str | None = None
    resume_token: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HumanGateResumeResult:
    """Outcome returned when resuming from a HITL checkpoint."""

    state: AgentState
    checkpoint: HydratedCheckpoint


@dataclass(slots=True)
class HumanGateService:
    """Evaluates router confidence + guardrail results to manage HITL pauses."""

    checkpoint_service: CheckpointService
    thresholds: Mapping[RouterRoute, float] = field(default_factory=lambda: _DEFAULT_THRESHOLDS)
    checkpoint_type: str = "human_gate"
    event_emitter: EventEmitter | None = None
    clock: Clock = _utc_now

    async def evaluate(self, state: AgentState) -> HumanGateDecision:
        """Return updated state and pause metadata if HITL is required."""

        reason = self._resolve_reason(state)
        if reason is None:
            # Clear stale interrupt metadata so downstream nodes don't accidentally pause.
            cleaned_state = state.model_copy(update={"interrupt_reason": None})
            return HumanGateDecision(paused=False, state=cleaned_state)

        resume_token = self._generate_resume_token()
        annotated_state = state.model_copy(update={"interrupt_reason": reason})
        annotated_state = self._append_transcript_entry(
            annotated_state,
            event="pause",
            reason=reason,
            resume_token=resume_token,
            guardrail_codes=self._guardrail_codes(state.guardrail_findings),
        )
        metadata = self._build_checkpoint_metadata(annotated_state, reason)
        persisted_state, resume_token = await self.checkpoint_service.pause_for_hitl(
            annotated_state,
            checkpoint_type=self.checkpoint_type,
            resume_token=resume_token,
            metadata=metadata,
        )
        persisted_state = self._attach_checkpoint_id_to_latest_entry(persisted_state)

        payload = {
            "event": "hitl_pause",
            "conversation_id": persisted_state.conversation_id,
            "checkpoint_id": persisted_state.checkpoint_id,
            "resume_token": resume_token,
            "reason": reason,
            "route": persisted_state.route.value if persisted_state.route else None,
            "confidence": persisted_state.route_confidence,
            "timestamp": self.clock().isoformat(),
        }
        await self._emit(payload)
        return HumanGateDecision(
            paused=True,
            state=persisted_state,
            reason=reason,
            resume_token=resume_token,
            payload=payload,
        )

    async def resume_from_hitl(
        self, conversation_id: str, resume_token: str
    ) -> HumanGateResumeResult:
        """Hydrate a paused checkpoint, append transcript metadata, and emit resume event."""

        checkpoint = await self.checkpoint_service.resume_from_hitl(conversation_id, resume_token)
        state = checkpoint.state.model_copy(update={"interrupt_reason": None})
        state = self._append_transcript_entry(
            state,
            event="resume",
            reason="hitl_resume",
            resume_token=checkpoint.metadata.consumed_resume_token,
            guardrail_codes=[],
        )
        state = self._attach_checkpoint_id_to_latest_entry(
            state, checkpoint_id=checkpoint.checkpoint_id
        )
        payload = {
            "event": "hitl_resume",
            "conversation_id": state.conversation_id,
            "checkpoint_id": checkpoint.checkpoint_id,
            "resume_token": checkpoint.metadata.consumed_resume_token,
            "timestamp": self.clock().isoformat(),
        }
        await self._emit(payload)
        return HumanGateResumeResult(state=state, checkpoint=checkpoint)

    def _resolve_reason(self, state: AgentState) -> str | None:
        if not state.guardrails_passed or self._has_blocking_guardrail(state.guardrail_findings):
            return "guardrail_violation"
        if state.route == RouterRoute.ESCALATE:
            return "manual_escalation"
        threshold = self.thresholds.get(state.route or RouterRoute.INFORMATIONAL, 0.6)
        confidence = state.route_confidence or 0.0
        if confidence < threshold:
            return "low_confidence"
        return None

    def _has_blocking_guardrail(self, findings: list[GuardrailViolation]) -> bool:
        return any(violation.severity == GuardrailSeverity.ERROR for violation in findings)

    def _guardrail_codes(self, findings: list[GuardrailViolation]) -> list[str]:
        return [violation.code for violation in findings]

    def _build_checkpoint_metadata(self, state: AgentState, reason: str) -> dict[str, Any]:
        return {
            "resume_kind": "hitl",
            "reason": reason,
            "route": state.route.value if state.route else None,
            "confidence": state.route_confidence,
            "guardrail_codes": self._guardrail_codes(state.guardrail_findings),
            "captured_at": self.clock().isoformat(),
        }

    def _append_transcript_entry(
        self,
        state: AgentState,
        *,
        event: Literal["pause", "resume"],
        reason: str,
        resume_token: str | None,
        guardrail_codes: list[str],
        checkpoint_id: str | None = None,
    ) -> AgentState:
        entries = list(state.hitl_transcript)
        entries.append(
            HitlTranscriptEntry(
                event=event,
                reason=reason,
                resume_token=resume_token,
                route=state.route,
                guardrail_codes=guardrail_codes,
                confidence=state.route_confidence,
                checkpoint_id=checkpoint_id or state.checkpoint_id,
                metadata={"checkpoint_type": self.checkpoint_type},
            )
        )
        return state.model_copy(update={"hitl_transcript": entries})

    def _attach_checkpoint_id_to_latest_entry(
        self, state: AgentState, *, checkpoint_id: str | None = None
    ) -> AgentState:
        if not state.hitl_transcript:
            return state
        entries = list(state.hitl_transcript)
        latest = entries[-1].model_copy(
            update={"checkpoint_id": checkpoint_id or state.checkpoint_id}
        )
        entries[-1] = latest
        return state.model_copy(update={"hitl_transcript": entries})

    def _generate_resume_token(self) -> str:
        return uuid4().hex

    async def _emit(self, payload: Mapping[str, Any]) -> None:
        if self.event_emitter is None:
            return
        await self.event_emitter(payload["event"], payload)
