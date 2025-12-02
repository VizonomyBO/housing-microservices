from __future__ import annotations

import polars as pl
import pytest
from langchain_core.messages import HumanMessage

from state.agent_state import AgentState, MessageSnapshot
from subgraphs.numerical.polars_executor_node import PolarsExecutionError, PolarsExecutorNode


def _table_resolver(_: AgentState) -> dict[str, pl.LazyFrame]:
    frame = pl.DataFrame(
        {
            "country": ["LBR", "GHA"],
            "gdp": [1.2, 3.4],
        }
    )
    return {"gdp": frame.lazy()}


def _base_state(sql: str) -> AgentState:
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hello"))],
        conversation_id="conv-polars",
        numerical_sql=sql,
        numerical_selected_table="gdp",
    )


@pytest.mark.asyncio
async def test_executes_sql_and_records_metrics() -> None:
    node = PolarsExecutorNode(table_resolver=_table_resolver)
    state = _base_state("SELECT country, gdp FROM gdp WHERE gdp > 2")

    updates = await node(state)

    assert updates["numerical_result_rows"] == [{"country": "GHA", "gdp": 3.4}]
    assert updates["subgraph_metrics"]["numerical.polars.row_count"] == 1
    assert updates["numerical_result_metrics"]["table_aliases"] == ["gdp"]


@pytest.mark.asyncio
async def test_raises_on_invalid_sql() -> None:
    node = PolarsExecutorNode(table_resolver=_table_resolver)
    state = _base_state("SELECT missing FROM gdp")

    with pytest.raises(PolarsExecutionError):
        await node(state)
