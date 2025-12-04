"""Polars executor node for Numerical subgraph queries."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any, cast

import polars as pl

from state.agent_state import AgentState
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import (
    add_metadata,
    emit_telemetry_snapshot,
    lifecycle_span,
)

LazyFrameMap = Mapping[str, pl.LazyFrame]
TableResolver = Callable[[AgentState], LazyFrameMap | Awaitable[LazyFrameMap]]

logger = logging.getLogger(__name__)


class PolarsExecutionError(RuntimeError):
    """Raised when Polars execution fails."""


@dataclass(slots=True)
class PolarsExecutorNode:
    """LangGraph node that executes Polars SQL inside a background thread."""

    table_resolver: TableResolver
    interrupt_reason: str = "numerical_polars_error"
    result_preview_rows: int = 5

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        query = (state.numerical_sql or "").strip()
        if not query:
            raise PolarsExecutionError("PolarsExecutor requires numerical_sql in state")
        tables = await self._resolve_tables(state)
        selected_alias = state.numerical_selected_table
        if selected_alias and selected_alias in tables:
            tables = {selected_alias: tables[selected_alias]}
        if not tables:
            raise PolarsExecutionError("No tables available for Polars execution")
        async with lifecycle_span(
            emitter=sse_emitter,
            node="numerical_polars_executor",
            subgraph="numerical",
            metadata={"table_aliases": list(tables.keys())},
        ):
            start = perf_counter()
            try:
                rows = await asyncio.to_thread(self._execute_query, query, tables)
            except Exception as exc:  # pragma: no cover - polars internal errors
                message = f"Polars SQL execution failed: {exc}"
                raise PolarsExecutionError(message) from exc
            duration_ms = (perf_counter() - start) * 1000
            row_count = len(rows)
            normalized_query = " ".join(query.split())
            log_query = normalized_query if len(normalized_query) <= 400 else f"{normalized_query[:397]}..."
            logger.info(
                "numerical SQL executed (tables=%s rows=%s query=%s)",
                ",".join(sorted(tables.keys())),
                row_count,
                log_query,
            )
            metrics = dict(state.subgraph_metrics)
            metrics.update(
                {
                    "numerical.polars.execution_ms": round(duration_ms, 3),
                    "numerical.polars.row_count": row_count,
                    "numerical.sql.executed": metrics.get("numerical.sql.executed", 0) + 1,
                    "numerical.sql.rows": row_count,
                }
            )
            result_metrics = dict(state.numerical_result_metrics)
            result_metrics.update(
                {
                    "execution_ms": round(duration_ms, 3),
                    "row_count": row_count,
                    "table_aliases": list(tables.keys()),
                    "sql_query": query,
                }
            )
            add_metadata(
                execution_ms=round(duration_ms, 3),
                row_count=row_count,
                sql_query=normalized_query,
            )
            await emit_telemetry_snapshot(
                sse_emitter,
                metrics={
                    "numerical.polars.execution_ms": round(duration_ms, 3),
                    "numerical.sql.executed": metrics["numerical.sql.executed"],
                    "numerical.sql.rows": row_count,
                },
                labels={"table_aliases": ",".join(sorted(tables.keys()))},
            )
            trace = dict(state.numerical_trace)
            preview_rows = rows[: self.result_preview_rows]
            executor_trace = {
                "row_count": row_count,
                "table_aliases": list(tables.keys()),
                "execution_ms": round(duration_ms, 3),
                "result_preview": preview_rows,
                "sql_query": query,
            }
            if not trace.get("sql_queries"):
                trace["sql_queries"] = [query]
            trace.update(
                {
                    "executor": executor_trace,
                    "table_results": preview_rows,
                }
            )
            return {
                "numerical_result_rows": rows,
                "numerical_result_metrics": result_metrics,
                "subgraph_metrics": metrics,
                "numerical_trace": trace,
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
