from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest
from langchain_core.messages import HumanMessage

from guardrails.models import GuardrailCode, GuardrailSeverity, GuardrailViolation, RouterRoute
from hitl import HumanGateService
from nodes.human.human_gate_node import HumanGateNode
from repositories.agent_checkpoint_repository import (
    CheckpointMetadata,
    HydratedCheckpoint,
)
from services.checkpoint_service import CheckpointService
from state.agent_state import AgentState, MessageSnapshot


class StubCheckpointService:
    def __init__(self) -> None:
        self.saved_states: list[AgentState] = []
        self.saved_metadata: list[dict[str, object]] = []
        self.resume_lookup: dict[str, HydratedCheckpoint] = {}

    async def pause_for_hitl(
        self,
        state: AgentState,
        *,
        checkpoint_type: str,
        resume_token: str | None = None,
        metadata: dict[str, object] | None = None,
        **_: object,
    ) -> tuple[AgentState, str]:
        token = resume_token or "token"
        checkpoint_id = f"chk-{len(self.saved_states) + 1}"
        updated_state = state.model_copy(update={"checkpoint_id": checkpoint_id})
        checkpoint = HydratedCheckpoint(
            checkpoint_id=checkpoint_id,
            state=updated_state,
            documents=[],
            metadata=CheckpointMetadata(resume_token=token),
        )
        self.saved_states.append(updated_state)
        if metadata:
            self.saved_metadata.append(metadata)
        self.resume_lookup[token] = checkpoint
        return updated_state, token

    async def resume_from_hitl(self, conversation_id: str, resume_token: str) -> HydratedCheckpoint:
        checkpoint = self.resume_lookup[resume_token]
        checkpoint.metadata.consumed_resume_token = resume_token
        return checkpoint


class EventRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, object]]] = []

    async def emit(self, event: str, payload: Mapping[str, object]) -> None:
        self.events.append((event, payload))


def _agent_state(
    *,
    confidence: float,
    route: RouterRoute = RouterRoute.INFORMATIONAL,
    guardrail_violation: bool = False,
) -> AgentState:
    findings: list[GuardrailViolation] = []
    passed = True
    if guardrail_violation:
        passed = False
        findings.append(
            GuardrailViolation(
                code=GuardrailCode.PROMPT_INJECTION,
                severity=GuardrailSeverity.ERROR,
                message="blocked",
            )
        )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hello"))],
        conversation_id="conv-123",
        route=route,
        route_confidence=confidence,
        guardrails_passed=passed,
        guardrail_findings=findings,
    )


@pytest.mark.asyncio
async def test_low_confidence_triggers_hitl_pause() -> None:
    checkpoint = StubCheckpointService()
    recorder = EventRecorder()
    service = HumanGateService(
        checkpoint_service=cast(CheckpointService, checkpoint),
        event_emitter=recorder.emit,
    )
    node = HumanGateNode(service=service)
    state = _agent_state(confidence=0.2)

    result = await node(state)

    assert result["interrupt_reason"] == "low_confidence"
    assert result["checkpoint_id"].startswith("chk-")
    assert result["resume_token"] is not None
    transcript = result["hitl_transcript"]
    assert len(transcript) == 1
    assert transcript[0].event == "pause"
    assert recorder.events[0][0] == "hitl_pause"


@pytest.mark.asyncio
async def test_guardrail_violation_overrides_confidence() -> None:
    checkpoint = StubCheckpointService()
    recorder = EventRecorder()
    service = HumanGateService(
        checkpoint_service=cast(CheckpointService, checkpoint),
        event_emitter=recorder.emit,
    )
    node = HumanGateNode(service=service)
    state = _agent_state(confidence=0.95, guardrail_violation=True)

    result = await node(state)

    assert result["interrupt_reason"] == "guardrail_violation"
    assert recorder.events[0][0] == "hitl_pause"


@pytest.mark.asyncio
async def test_resume_from_hitl_appends_transcript_entry() -> None:
    checkpoint = StubCheckpointService()
    recorder = EventRecorder()
    service = HumanGateService(
        checkpoint_service=cast(CheckpointService, checkpoint),
        event_emitter=recorder.emit,
    )
    node = HumanGateNode(service=service)
    state = _agent_state(confidence=0.15)
    pause_result = await node(state)

    resumed_state = await node.resume_from_hitl(state.conversation_id, pause_result["resume_token"])

    assert resumed_state.interrupt_reason is None
    assert len(resumed_state.hitl_transcript) == 2
    assert resumed_state.hitl_transcript[-1].event == "resume"
    assert recorder.events[-1][0] == "hitl_resume"


@pytest.mark.asyncio
async def test_high_confidence_bypasses_human_gate() -> None:
    checkpoint = StubCheckpointService()
    recorder = EventRecorder()
    service = HumanGateService(
        checkpoint_service=cast(CheckpointService, checkpoint),
        event_emitter=recorder.emit,
    )
    node = HumanGateNode(service=service)
    state = _agent_state(confidence=0.9)

    result = await node(state)

    assert result["interrupt_reason"] is None
    assert result["hitl_transcript"] == []
    assert recorder.events == []
