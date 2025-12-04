"""Text-to-SQL node for the Numerical subgraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from guardrails.models import GuardrailCode, GuardrailSeverity, GuardrailViolation
from state.agent_state import AgentState, NumericalTable, WorkflowPlan
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, emit_demo_mode_event, lifecycle_span


class TextToSQLError(RuntimeError):
    """Raised when prerequisites for the TextToSQL node are missing."""


class TextToSQLGuardrail(RuntimeError):
    """Raised when the generated SQL violates schema or policy guardrails."""


@dataclass(slots=True)
class SqlGenerationRequest:
    """Inputs forwarded to the SQL generator implementation."""

    prompt: str
    normalized_prompt: str
    table: NumericalTable
    workflow_plan: WorkflowPlan | None
    retry_counter: int
    previous_error: str | None


@dataclass(slots=True)
class SqlGenerationResult:
    """Outputs returned by the SQL generator implementation."""

    sql: str
    tables: list[str]
    columns: dict[str, list[str]]
    reasoning: str | None = None
    confidence: float | None = None
    table_specs: list[dict[str, Any]] = field(default_factory=list)
    sql_queries: list[str] = field(default_factory=list)


class SqlGeneratorProtocol(Protocol):
    """Adapter interface for LLM/text-to-SQL tools."""

    async def generate(self, request: SqlGenerationRequest) -> SqlGenerationResult: ...


@dataclass(slots=True)
class NumericalPromptBuilder:
    """Deterministic prompt builder for textual-to-SQL conversions."""

    max_plan_steps: int = 3
    max_sample_rows: int = 3

    def build(
        self,
        *,
        normalized_prompt: str,
        table: NumericalTable,
        workflow_plan: WorkflowPlan | None,
        previous_error: str | None,
    ) -> str:
        lines: list[str] = [
            "You are a numerical analyst that emits Polars SQL queries.",
            "You MUST return a SQL query that can run directly against the provided table specs.",
            "Never perform arithmetic or summarization outside SQL; do not answer in prose.",
            "Return only SQL without commentary.",
            "If data is insufficient, emit a valid SQL query against the provided table alias that returns zero rows (for example, add `WHERE 1=0`).",
            "Direct answers, natural-language explanations, or calculations outside SQL will be rejected.",
            f"User question: {normalized_prompt.strip()}",
            "Use the selected table only; joins are not yet supported.",
            f"Table alias: {table.alias}",
            "Columns:",
        ]
        for column in table.columns:
            description = f" - {column.description}" if column.description else ""
            bounds: list[str] = []
            if column.min_value is not None:
                bounds.append(f">= {column.min_value}")
            if column.max_value is not None:
                bounds.append(f"<= {column.max_value}")
            bound_clause = f" | bounds: {' ,'.join(bounds)}" if bounds else ""
            lines.append(f"- {column.name} ({column.data_type}){description}{bound_clause}")
        if table.sample_rows:
            lines.append("Sample rows:")
            for row in table.sample_rows[: self.max_sample_rows]:
                lines.append(f"- {row}")
        if workflow_plan:
            steps = [step.description for step in workflow_plan.steps[: self.max_plan_steps]]
            if steps:
                lines.append("Workflow guidance:")
                for idx, step in enumerate(steps, start=1):
                    lines.append(f"{idx}. {step}")
        if previous_error:
            lines.append(f"Previous error to avoid: {previous_error}")
        lines.append("Return Polars SQL compatible with SQLContext.")
        return "\n".join(lines)


@dataclass(slots=True)
class TextToSQLNode:
    """LangGraph node that converts natural language to Polars SQL with guardrails."""

    generator: SqlGeneratorProtocol
    prompt_builder: NumericalPromptBuilder = field(default_factory=NumericalPromptBuilder)
    interrupt_reason: str = "numerical_sql_guardrail"

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        normalized = state.normalized_input
        if normalized is None:
            raise TextToSQLError("TextToSQL node requires normalized_input in AgentState")
        table = self._selected_table(state)
        requires_sql = state.requires_sql
        maybe_skip = await self._maybe_skip_for_demo(state, sse_emitter)
        if maybe_skip is not None:
            return maybe_skip
        async with lifecycle_span(
            emitter=sse_emitter,
            node="numerical_text_to_sql",
            subgraph="numerical",
            metadata={"table": table.alias},
        ):
            prompt = self.prompt_builder.build(
                normalized_prompt=normalized.normalized_prompt,
                table=table,
                workflow_plan=state.workflow_plan,
                previous_error=self._previous_error(state),
            )
            request = SqlGenerationRequest(
                prompt=prompt,
                normalized_prompt=normalized.normalized_prompt,
                table=table,
                workflow_plan=state.workflow_plan,
                retry_counter=state.retry_counter,
                previous_error=self._previous_error(state),
            )
            result = await self.generator.generate(request)
            guardrail_message = self._validate_result(table, result)
            sql_queries = self._normalize_queries(result)
            if requires_sql and not sql_queries:
                raise TextToSQLError(
                    "Router required SQL execution but SQL planner returned no queries"
                )
            table_specs = self._normalize_table_specs(table, result.table_specs)
            add_metadata(prompt_chars=len(prompt), retry_counter=state.retry_counter)
            if guardrail_message:
                add_metadata(guardrail_triggered=True, guardrail_reason=guardrail_message)
                return self._serialize_guardrail(state, guardrail_message, result)
            metrics = dict(state.subgraph_metrics)
            metrics.update(
                {
                    "numerical.text_to_sql.prompt_chars": len(prompt),
                    "numerical.text_to_sql.retry": state.retry_counter,
                    "numerical.text_to_sql.tables": len(result.tables),
                }
            )
            add_metadata(guardrail_triggered=False, table_count=len(result.tables))
            trace = dict(state.numerical_trace)
            trace.update(
                {
                    "table_specs": table_specs,
                    "sql_queries": sql_queries,
                    "planner_reasoning": result.reasoning,
                }
            )
            if "chunk_ids" not in trace and table_specs:
                trace["chunk_ids"] = table_specs[0].get("chunk_ids", [])
            return {
                "numerical_sql": (sql_queries[0] if sql_queries else result.sql.strip()),
                "numerical_sql_reasoning": result.reasoning,
                "subgraph_metrics": metrics,
                "numerical_trace": trace,
            }

    def _selected_table(self, state: AgentState) -> NumericalTable:
        alias = state.numerical_selected_table
        if not state.numerical_tables or alias is None:
            raise TextToSQLError("Numerical table selection missing for TextToSQL node")
        for table in state.numerical_tables:
            if alias in {table.alias, table.table_id}:
                return table
        raise TextToSQLError(f"Selected table alias '{alias}' not found in numerical_tables")

    def _normalize_table_specs(
        self, table: NumericalTable, requested_specs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        default_spec = self._default_table_spec(table)
        if not requested_specs:
            return [default_spec]
        normalized: list[dict[str, Any]] = []
        for spec in requested_specs:
            merged = dict(default_spec)
            merged.update(spec)
            if not merged.get("chunk_ids"):
                merged["chunk_ids"] = default_spec.get("chunk_ids", [])
            if not merged.get("document_ids"):
                merged["document_ids"] = default_spec.get("document_ids", [])
            if not merged.get("column_names"):
                merged["column_names"] = default_spec.get("column_names", [])
            normalized.append(merged)
        return normalized

    def _default_table_spec(self, table: NumericalTable) -> dict[str, Any]:
        metadata = dict(table.metadata or {})
        document_ids = metadata.get("document_ids") or metadata.get("documents") or []
        chunk_ids = metadata.get("chunk_ids") or metadata.get("chunks") or []
        return {
            "table_id": table.table_id,
            "table_name": table.table_name,
            "alias": table.alias,
            "row_count": table.row_count,
            "column_names": [column.name for column in table.columns],
            "document_ids": document_ids,
            "chunk_ids": chunk_ids,
            "metadata": metadata,
        }

    def _normalize_queries(self, result: SqlGenerationResult) -> list[str]:
        candidates = result.sql_queries or ([result.sql] if result.sql else [])
        return [query.strip() for query in candidates if query and query.strip()]

    def _previous_error(self, state: AgentState) -> str | None:
        if not state.error_log:
            return None
        return state.error_log[-1]

    def _validate_result(self, table: NumericalTable, result: SqlGenerationResult) -> str | None:
        sql = result.sql.strip()
        if not sql:
            return "Generated SQL was empty"
        allowed_aliases = {table.alias, table.table_id, table.table_name}
        referenced_tables = {item.lower() for item in result.tables}
        normalized_allowed = {alias.lower() for alias in allowed_aliases if alias}
        if not referenced_tables:
            referenced_tables = {table.alias.lower()}
        if len(referenced_tables - normalized_allowed) > 0:
            return "SQL references unsupported tables"
        if len(referenced_tables) > 1:
            return "Joins across multiple tables are not allowed"
        normalized_sql = sql.upper()
        if " JOIN " in normalized_sql or " UNION " in normalized_sql:
            return "JOIN/UNION statements are not allowed yet"
        allowed_columns = {column.name.lower() for column in table.columns}
        referenced_columns = set()
        for columns in result.columns.values():
            for column in columns:
                referenced_columns.add(column.lower())
        invalid_columns = referenced_columns - allowed_columns
        if invalid_columns:
            return "SQL references columns outside the selected schema"
        return None

    def _serialize_guardrail(
        self,
        state: AgentState,
        message: str,
        result: SqlGenerationResult,
    ) -> dict[str, Any]:
        violation = GuardrailViolation(
            code=GuardrailCode.NUMERICAL_SQL,
            severity=GuardrailSeverity.ERROR,
            message=message,
            details={
                "sql": result.sql,
                "tables": result.tables,
                "columns": result.columns,
            },
        )
        findings = list(state.guardrail_findings)
        findings.append(violation)
        error_log = list(state.error_log)
        error_log.append(message)
        return {
            "guardrail_findings": findings,
            "guardrails_passed": False,
            "error_log": error_log,
            "interrupt_reason": self.interrupt_reason,
            "next_subgraph": "human_gate",
        }

    async def _maybe_skip_for_demo(
        self, state: AgentState, sse_emitter: SSEEmitter | None
    ) -> dict[str, Any] | None:
        flags = state.reduced_scope_flags
        if state.requires_sql:
            if flags.should_skip_capability("numerical"):
                add_metadata(reduced_scope_sql_override=True, capability="numerical")
            return None
        if not flags.should_skip_capability("numerical"):
            return None
        if sse_emitter is not None and flags.emit_demo_events:
            await emit_demo_mode_event(
                sse_emitter,
                capability="numerical",
                metadata={"node": "numerical_text_to_sql"},
            )
        metrics = dict(state.subgraph_metrics)
        key = "numerical.demo_mode_skipped"
        metrics[key] = metrics.get(key, 0) + 1
        add_metadata(reduced_scope_skip=True, capability="numerical")
        return {
            "next_subgraph": "informational_subgraph",
            "subgraph_metrics": metrics,
            "guardrails_passed": True,
        }


__all__ = [
    "NumericalPromptBuilder",
    "SqlGenerationRequest",
    "SqlGenerationResult",
    "SqlGeneratorProtocol",
    "TextToSQLError",
    "TextToSQLGuardrail",
    "TextToSQLNode",
]
