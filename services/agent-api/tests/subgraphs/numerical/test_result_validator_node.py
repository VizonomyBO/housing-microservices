from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from hitl.human_gate_service import HumanGateDecision
from state.agent_state import AgentState, MessageSnapshot, NumericalTable, NumericalTableColumn
from subgraphs.numerical.result_validator_node import ResultValidatorNode


class StubHumanGate:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(
        self, state: AgentState, *, event_emitter=None  # type: ignore[unused-argument]
    ) -> HumanGateDecision:
        self.calls += 1
        return HumanGateDecision(paused=False, state=state)


def _table() -> NumericalTable:
    return NumericalTable(
        table_id="tbl-gdp",
        table_name="GDP",
        alias="gdp",
        columns=[
            NumericalTableColumn(name="country", data_type="text"),
            NumericalTableColumn(name="gdp", data_type="float", min_value=0.0, max_value=100.0),
        ],
    )


def _base_state(rows: list[dict[str, float | str]]) -> AgentState:
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="numerical"))],
        conversation_id="conv-validate",
        numerical_tables=[_table()],
        numerical_selected_table="gdp",
        numerical_result_rows=rows,
    )


@pytest.mark.asyncio
async def test_valid_results_emit_artifacts() -> None:
    node = ResultValidatorNode()
    state = _base_state([{"country": "LBR", "gdp": 12.0}, {"country": "GHA", "gdp": 20.0}])

    updates = await node(state)

    assert updates["guardrails_passed"] is True
    assert len(updates["numerical_artifacts"]) >= 1
    assert updates["numerical_artifacts"][0].attachment_type == "table"


@pytest.mark.asyncio
async def test_out_of_bounds_routes_to_human_gate() -> None:
    human_gate = StubHumanGate()
    node = ResultValidatorNode(human_gate=human_gate)
    state = _base_state([{"country": "LBR", "gdp": 150.0}])

    updates = await node(state)

    assert updates["guardrails_passed"] is False
    assert updates["next_subgraph"] == "human_gate"
    assert human_gate.calls == 1
