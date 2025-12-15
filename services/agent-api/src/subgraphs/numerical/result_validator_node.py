"""Result validation node for Numerical subgraph outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from guardrails.models import GuardrailCode, GuardrailSeverity, GuardrailViolation
from hitl.human_gate_service import EventEmitter, HumanGateDecision
from state.agent_state import AgentState, NumericalTable
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, emit_demo_mode_event, lifecycle_span

from .artifacts import build_numerical_artifacts


class NumericalValidationError(RuntimeError):
    """Raised when prerequisites for the numerical validator are missing."""


class HumanGateEvaluator(Protocol):
    """Subset of HumanGateService used by this node."""

    async def evaluate(
        self, state: AgentState, *, event_emitter: EventEmitter | None = None
    ) -> HumanGateDecision: ...


@dataclass(slots=True)
class ResultValidatorNode:
    """Validates numerical outputs and escalates to HITL when guardrails fail."""

    human_gate: HumanGateEvaluator | None = None
    interrupt_reason: str = "numerical_validation"
    table_preview_rows: int = 20

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        table = self._selected_table(state)
        rows = list(state.numerical_result_rows)
        skip = await self._maybe_skip_for_demo(state, sse_emitter)
        if skip is not None:
            return skip
        async with lifecycle_span(
            emitter=sse_emitter,
            node="numerical_result_validator",
            subgraph="numerical",
            metadata={"table_alias": table.alias},
        ):
            if not rows:
                add_metadata(validation="no_rows")
                return await self._escalate(
                    state,
                    table,
                    "Numerical execution returned no rows to validate",
                    sse_emitter=sse_emitter,
                )
            violations = self._validate_rows(rows, table)
            if violations:
                add_metadata(validation="violations", violation_count=len(violations))
                return await self._escalate(state, table, violations, sse_emitter=sse_emitter)
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
            add_metadata(validation="passed", row_count=len(rows))
            trace = self._merge_trace(
                state,
                validator={
                    "status": "passed",
                    "row_count": len(rows),
                    "table_id": table.table_id,
                },
            )
            return {
                "guardrails_passed": True,
                "numerical_artifacts": artifacts,
                "subgraph_metrics": metrics,
                "numerical_trace": trace,
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
        *,
        sse_emitter: SSEEmitter | None = None,
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
        trace = self._merge_trace(
            state,
            validator={
                "status": "failed",
                "table_id": table.table_id,
                "violations": details,
            },
        )
        updates: dict[str, Any] = {
            "guardrail_findings": findings,
            "guardrails_passed": False,
            "error_log": error_log,
            "interrupt_reason": self.interrupt_reason,
            "next_subgraph": "human_gate",
            "numerical_trace": trace,
        }
        annotated_state = state.model_copy(update=updates)
        if self.human_gate is None:
            return updates
        emitter = sse_emitter.as_event_emitter() if sse_emitter else None
        decision = await self.human_gate.evaluate(annotated_state, event_emitter=emitter)
        hitl_updates: dict[str, Any] = {
            "interrupt_reason": decision.state.interrupt_reason,
            "hitl_transcript": decision.state.hitl_transcript,
        }
        if decision.paused:
            hitl_updates["checkpoint_id"] = decision.state.checkpoint_id
        return {**updates, **hitl_updates}

    async def _maybe_skip_for_demo(
        self, state: AgentState, sse_emitter: SSEEmitter | None
    ) -> dict[str, Any] | None:
        flags = state.reduced_scope_flags
        if state.requires_sql:
            if flags.should_skip_capability("numerical"):
                add_metadata(reduced_scope_sql_override=True, capability="numerical_validator")
            return None
        if not flags.should_skip_capability("numerical"):
            return None
        if sse_emitter is not None and flags.emit_demo_events:
            await emit_demo_mode_event(
                sse_emitter,
                capability="numerical",
                metadata={"node": "numerical_result_validator"},
            )
        add_metadata(reduced_scope_skip=True, capability="numerical")
        metrics = dict(state.subgraph_metrics)
        key = "numerical.demo_mode_skipped"
        metrics[key] = metrics.get(key, 0) + 1
        return {
            "subgraph_metrics": metrics,
            "next_subgraph": "informational_subgraph",
            "guardrails_passed": True,
        }

    def _merge_trace(self, state: AgentState, **entries: Any) -> dict[str, Any]:
        trace = dict(state.numerical_trace)
        trace.update(entries)
        return trace


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


__all__ = ["HumanGateEvaluator", "NumericalValidationError", "ResultValidatorNode"]
