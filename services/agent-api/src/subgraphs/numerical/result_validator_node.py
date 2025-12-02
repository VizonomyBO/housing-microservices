"""Result validation node for Numerical subgraph outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from guardrails.models import GuardrailCode, GuardrailSeverity, GuardrailViolation
from hitl.human_gate_service import HumanGateDecision
from state.agent_state import AgentState, NumericalTable

from .artifacts import build_numerical_artifacts


class NumericalValidationError(RuntimeError):
    """Raised when prerequisites for the numerical validator are missing."""


class HumanGateEvaluator(Protocol):
    """Subset of HumanGateService used by this node."""

    async def evaluate(self, state: AgentState) -> HumanGateDecision: ...


@dataclass(slots=True)
class ResultValidatorNode:
    """Validates numerical outputs and escalates to HITL when guardrails fail."""

    human_gate: HumanGateEvaluator | None = None
    interrupt_reason: str = "numerical_validation"
    table_preview_rows: int = 20

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        table = self._selected_table(state)
        rows = list(state.numerical_result_rows)
        if not rows:
            return await self._escalate(
                state,
                table,
                "Numerical execution returned no rows to validate",
            )
        violations = self._validate_rows(rows, table)
        if violations:
            return await self._escalate(state, table, violations)
        artifacts = build_numerical_artifacts(
            table,
            rows,
            table_preview_rows=self.table_preview_rows,
        )
        metrics = dict(state.subgraph_metrics)
        metrics.update(
            {
                "numerical.validation.rows": len(rows),
                "numerical.validation.columns": len(table.columns),
            }
        )
        return {
            "guardrails_passed": True,
            "numerical_artifacts": artifacts,
            "subgraph_metrics": metrics,
        }

    def _selected_table(self, state: AgentState) -> NumericalTable:
        alias = state.numerical_selected_table
        if not state.numerical_tables or alias is None:
            raise NumericalValidationError(
                "ResultValidator requires numerical_tables and a selected alias"
            )
        for table in state.numerical_tables:
            if alias in {table.alias, table.table_id}:
                return table
        raise NumericalValidationError(f"Table alias '{alias}' missing from AgentState")

    def _validate_rows(
        self, rows: list[dict[str, Any]], table: NumericalTable
    ) -> list[dict[str, Any]]:
        allowed = {column.name: column for column in table.columns}
        violations: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            unexpected = set(row.keys()) - set(allowed.keys())
            if unexpected:
                violations.append(
                    {
                        "row": idx,
                        "issue": "unexpected_columns",
                        "columns": sorted(unexpected),
                    }
                )
            for name, column in allowed.items():
                if name not in row:
                    continue
                value = row[name]
                if value is None:
                    continue
                if column.min_value is not None and _is_number(value) and value < column.min_value:
                    violations.append(
                        {
                            "row": idx,
                            "issue": "below_min",
                            "column": name,
                            "value": value,
                            "min": column.min_value,
                        }
                    )
                if column.max_value is not None and _is_number(value) and value > column.max_value:
                    violations.append(
                        {
                            "row": idx,
                            "issue": "above_max",
                            "column": name,
                            "value": value,
                            "max": column.max_value,
                        }
                    )
        return violations

    async def _escalate(
        self,
        state: AgentState,
        table: NumericalTable,
        violations: str | list[dict[str, Any]],
    ) -> dict[str, Any]:
        details: list[dict[str, Any]]
        if isinstance(violations, str):
            details = [{"message": violations, "table_id": table.table_id}]
            message = violations
        else:
            details = violations
            message = "Numerical results failed validation"
        violation = GuardrailViolation(
            code=GuardrailCode.NUMERICAL_VALIDATION,
            severity=GuardrailSeverity.ERROR,
            message=message,
            details={"violations": details, "table_id": table.table_id},
        )
        findings = list(state.guardrail_findings)
        findings.append(violation)
        error_log = list(state.error_log)
        error_log.append(message)
        updates: dict[str, Any] = {
            "guardrail_findings": findings,
            "guardrails_passed": False,
            "error_log": error_log,
            "interrupt_reason": self.interrupt_reason,
            "next_subgraph": "human_gate",
        }
        annotated_state = state.model_copy(update=updates)
        if self.human_gate is None:
            return updates
        decision = await self.human_gate.evaluate(annotated_state)
        hitl_updates: dict[str, Any] = {
            "interrupt_reason": decision.state.interrupt_reason,
            "hitl_transcript": decision.state.hitl_transcript,
        }
        if decision.paused:
            hitl_updates["checkpoint_id"] = decision.state.checkpoint_id
        return {**updates, **hitl_updates}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


__all__ = ["HumanGateEvaluator", "NumericalValidationError", "ResultValidatorNode"]
