from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from models.retrieval import NormalizedInput, TenantScope
from state.agent_state import (
    AgentState,
    MessageSnapshot,
    NumericalTable,
    NumericalTableColumn,
    WorkflowPlan,
    WorkflowPlanStep,
)
from subgraphs.numerical.text_to_sql_node import (
    NumericalPromptBuilder,
    SqlGenerationRequest,
    SqlGenerationResult,
    TextToSQLNode,
)


class StubGenerator:
    def __init__(self, result: SqlGenerationResult) -> None:
        self.result = result
        self.requests: list[SqlGenerationRequest] = []

    async def generate(self, request: SqlGenerationRequest) -> SqlGenerationResult:  # type: ignore[override]
        self.requests.append(request)
        return self.result


def _base_state() -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt="Compute GDP delta",
        raw_prompt="Compute GDP delta",
        tenant_scope=TenantScope(conversation_id="conv-num", thread_id="thr-num"),
        attachment_refs=[],
        scope_hash="scope",
    )
    table = NumericalTable(
        table_id="tbl-gdp",
        table_name="GDP",
        alias="gdp",
        columns=[
            NumericalTableColumn(name="country", data_type="text"),
            NumericalTableColumn(name="gdp", data_type="float", min_value=0.0, max_value=100.0),
        ],
        sample_rows=[{"country": "LBR", "gdp": 12.1}],
        metadata={"document_ids": ["doc-1"], "chunk_ids": ["chunk-1"]},
    )
    plan = WorkflowPlan(
        plan_id="wf-1",
        version="v1",
        steps=[
            WorkflowPlanStep(key="step-1", description="Gather GDP", preconditions={}, artifacts={})
        ],
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-num",
        normalized_input=normalized,
        numerical_tables=[table],
        numerical_selected_table="gdp",
        workflow_plan=plan,
    )


@pytest.mark.asyncio
async def test_generates_sql_when_schema_valid() -> None:
    result = SqlGenerationResult(
        sql="SELECT country, gdp FROM gdp ORDER BY gdp DESC",
        tables=["gdp"],
        columns={"gdp": ["country", "gdp"]},
        reasoning="Need GDP order",
        sql_queries=["SELECT country, gdp FROM gdp ORDER BY gdp DESC"],
    )
    node = TextToSQLNode(generator=StubGenerator(result), prompt_builder=NumericalPromptBuilder())
    state = _base_state()

    updates = await node(state)

    assert updates["numerical_sql"] == "SELECT country, gdp FROM gdp ORDER BY gdp DESC"
    assert updates["numerical_sql_reasoning"] == "Need GDP order"
    assert updates["subgraph_metrics"]["numerical.text_to_sql.tables"] == 1
    trace = updates["numerical_trace"]
    assert trace["sql_queries"] == ["SELECT country, gdp FROM gdp ORDER BY gdp DESC"]
    assert trace["table_specs"][0]["table_id"] == "tbl-gdp"
    assert trace["table_specs"][0]["chunk_ids"] == ["chunk-1"]


@pytest.mark.asyncio
async def test_guardrail_triggers_on_join() -> None:
    result = SqlGenerationResult(
        sql="SELECT a.country FROM gdp a JOIN other b ON a.country=b.country",
        tables=["gdp", "other"],
        columns={"gdp": ["country"], "other": ["country"]},
        sql_queries=["SELECT a.country FROM gdp a JOIN other b ON a.country=b.country"],
    )
    node = TextToSQLNode(generator=StubGenerator(result))
    state = _base_state()

    updates = await node(state)

    assert updates["guardrails_passed"] is False
    assert updates["next_subgraph"] == "human_gate"
    assert updates["guardrail_findings"][-1].code.value == "numerical_sql"
