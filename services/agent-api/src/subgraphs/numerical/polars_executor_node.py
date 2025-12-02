"""Polars executor node for Numerical subgraph queries."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any, cast

import polars as pl

from state.agent_state import AgentState

LazyFrameMap = Mapping[str, pl.LazyFrame]
TableResolver = Callable[[AgentState], LazyFrameMap | Awaitable[LazyFrameMap]]


class PolarsExecutionError(RuntimeError):
    """Raised when Polars execution fails."""


@dataclass(slots=True)
class PolarsExecutorNode:
    """LangGraph node that executes Polars SQL inside a background thread."""

    table_resolver: TableResolver
    interrupt_reason: str = "numerical_polars_error"

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        query = (state.numerical_sql or "").strip()
        if not query:
            raise PolarsExecutionError("PolarsExecutor requires numerical_sql in state")
        tables = await self._resolve_tables(state)
        selected_alias = state.numerical_selected_table
        if selected_alias and selected_alias in tables:
            tables = {selected_alias: tables[selected_alias]}
        if not tables:
            raise PolarsExecutionError("No tables available for Polars execution")
        start = perf_counter()
        try:
            rows = await asyncio.to_thread(self._execute_query, query, tables)
        except Exception as exc:  # pragma: no cover - polars internal errors
            message = f"Polars SQL execution failed: {exc}"
            raise PolarsExecutionError(message) from exc
        duration_ms = (perf_counter() - start) * 1000
        row_count = len(rows)
        metrics = dict(state.subgraph_metrics)
        metrics.update(
            {
                "numerical.polars.execution_ms": round(duration_ms, 3),
                "numerical.polars.row_count": row_count,
            }
        )
        result_metrics = dict(state.numerical_result_metrics)
        result_metrics.update(
            {
                "execution_ms": round(duration_ms, 3),
                "row_count": row_count,
                "table_aliases": list(tables.keys()),
            }
        )
        return {
            "numerical_result_rows": rows,
            "numerical_result_metrics": result_metrics,
            "subgraph_metrics": metrics,
        }

    async def _resolve_tables(self, state: AgentState) -> LazyFrameMap:
        mapping = self.table_resolver(state)
        if inspect.isawaitable(mapping):
            mapping = await mapping
        return cast(LazyFrameMap, mapping)

    def _execute_query(self, query: str, tables: LazyFrameMap) -> list[dict[str, Any]]:
        ctx = pl.SQLContext()
        for alias, frame in tables.items():
            ctx.register(alias, frame)
        df = ctx.execute(query)
        if isinstance(df, pl.LazyFrame):
            df = df.collect()
        return df.to_dicts()


__all__ = ["PolarsExecutionError", "PolarsExecutorNode"]
