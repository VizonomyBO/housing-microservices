from __future__ import annotations

import polars as pl
import pytest
from langchain_core.messages import HumanMessage

from models.retrieval import NormalizedInput, TenantScope
from state.agent_state import (
    AgentState,
    MessageSnapshot,
    NumericalTable,
    NumericalTableColumn,
)
from subgraphs.numerical import ResultValidatorNode, TextToSQLNode
from subgraphs.numerical.polars_executor_node import PolarsExecutorNode
from subgraphs.numerical.text_to_sql_node import SqlGenerationRequest, SqlGenerationResult


class _SqlStub:
    def __init__(self, sql: str) -> None:
        self.result = SqlGenerationResult(
            sql=sql,
            tables=["ledger"],
            columns={"ledger": ["city", "utilization"]},
            sql_queries=[sql],
        )

    async def generate(self, request: SqlGenerationRequest) -> SqlGenerationResult:  # type: ignore[override]
        assert "MUST return a SQL query" in request.prompt
        return self.result


def _base_state() -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt="Group KPI values by city",
        raw_prompt="Group KPI values by city",
        tenant_scope=TenantScope(conversation_id="conv-num", thread_id="thr-num"),
        attachment_refs=[],
        scope_hash="scope",
    )
    table = NumericalTable(
        table_id="tbl-ledger",
        table_name="Ledger",
        alias="ledger",
        columns=[
            NumericalTableColumn(name="city", data_type="text"),
            NumericalTableColumn(name="utilization", data_type="float"),
        ],
        metadata={"document_ids": ["doc-1"], "chunk_ids": ["chunk-9"]},
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-num",
        normalized_input=normalized,
        numerical_tables=[table],
        numerical_selected_table="ledger",
        requires_sql=True,
    )


def _table_resolver(_: AgentState) -> dict[str, pl.LazyFrame]:
    frame = pl.DataFrame({"city": ["Austin", "Denton"], "utilization": [82, 71]})
    return {"ledger": frame.lazy()}


@pytest.mark.asyncio
async def test_numerical_trace_covers_entire_subgraph() -> None:
    text_node = TextToSQLNode(generator=_SqlStub("SELECT city, utilization FROM ledger"))
    executor = PolarsExecutorNode(table_resolver=_table_resolver)
    validator = ResultValidatorNode()

    state = _base_state()
    updates = await text_node(state)
    state = state.model_copy(update=updates)

    updates = await executor(state)
    state = state.model_copy(update=updates)

    updates = await validator(state)
    state = state.model_copy(update=updates)

    trace = state.numerical_trace
    assert trace["sql_queries"] == ["SELECT city, utilization FROM ledger"]
    assert trace["table_specs"][0]["chunk_ids"] == ["chunk-9"]
    assert trace["executor"]["row_count"] == 2
    assert trace["validator"]["status"] == "passed"
