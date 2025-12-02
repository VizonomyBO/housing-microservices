"""Text-to-SQL node for the Numerical subgraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from guardrails.models import GuardrailCode, GuardrailSeverity, GuardrailViolation
from state.agent_state import AgentState, NumericalTable, WorkflowPlan


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
            "Return only SQL without commentary.",
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

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        normalized = state.normalized_input
        if normalized is None:
            raise TextToSQLError("TextToSQL node requires normalized_input in AgentState")
        table = self._selected_table(state)
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
        if guardrail_message:
            return self._serialize_guardrail(state, guardrail_message, result)
        metrics = dict(state.subgraph_metrics)
        metrics.update(
            {
                "numerical.text_to_sql.prompt_chars": len(prompt),
                "numerical.text_to_sql.retry": state.retry_counter,
                "numerical.text_to_sql.tables": len(result.tables),
            }
        )
        return {
            "numerical_sql": result.sql.strip(),
            "numerical_sql_reasoning": result.reasoning,
            "subgraph_metrics": metrics,
        }

    def _selected_table(self, state: AgentState) -> NumericalTable:
        alias = state.numerical_selected_table
        if not state.numerical_tables or alias is None:
            raise TextToSQLError("Numerical table selection missing for TextToSQL node")
        for table in state.numerical_tables:
            if alias in {table.alias, table.table_id}:
                return table
        raise TextToSQLError(f"Selected table alias '{alias}' not found in numerical_tables")

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


__all__ = [
    "NumericalPromptBuilder",
    "SqlGenerationRequest",
    "SqlGenerationResult",
    "SqlGeneratorProtocol",
    "TextToSQLError",
    "TextToSQLGuardrail",
    "TextToSQLNode",
]
