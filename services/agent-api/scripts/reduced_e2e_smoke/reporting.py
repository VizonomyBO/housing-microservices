"""Reporting utilities for the reduced E2E smoke run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class StageResult:
    name: str
    success: bool
    latency_ms: float
    detail: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptRunResult:
    prompt_id: str
    capability: str
    mode: str
    success: bool
    latency_ms: float
    failures: list[str] = field(default_factory=list)
    response_excerpt: str | None = None
    judge_name: str | None = None
    judge_score: float | None = None
    judge_explanation: str | None = None
    requires_sql: bool = False
    sql_queries: list[str] = field(default_factory=list)
    sql_row_count: int | None = None
    sql_table_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class RunSummary:
    scenario: str
    version: str
    started_at: datetime
    finished_at: datetime
    stages: list[StageResult] = field(default_factory=list)
    prompts: list[PromptRunResult] = field(default_factory=list)
    telemetry: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        stage_success = all(stage.success for stage in self.stages)
        prompt_success = all(prompt.success for prompt in self.prompts) if self.prompts else True
        return stage_success and prompt_success

    def duration_ms(self) -> float:
        delta = self.finished_at - self.started_at
        return delta.total_seconds() * 1000

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario": self.scenario,
            "version": self.version,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_ms": self.duration_ms(),
            "success": self.success,
            "stages": [
                {
                    "name": stage.name,
                    "success": stage.success,
                    "latency_ms": stage.latency_ms,
                    "detail": stage.detail,
                    "metadata": stage.metadata,
                }
                for stage in self.stages
            ],
            "prompts": [
                {
                    "prompt_id": prompt.prompt_id,
                    "capability": prompt.capability,
                    "mode": prompt.mode,
                    "success": prompt.success,
                    "latency_ms": prompt.latency_ms,
                    "failures": prompt.failures,
                    "response_excerpt": prompt.response_excerpt,
                    "judge_name": prompt.judge_name,
                    "judge_score": prompt.judge_score,
                    "judge_explanation": prompt.judge_explanation,
                    "requires_sql": prompt.requires_sql,
                    "sql_queries": prompt.sql_queries,
                    "sql_row_count": prompt.sql_row_count,
                    "sql_table_results": prompt.sql_table_results,
                }
                for prompt in self.prompts
            ],
        }
        if self.telemetry:
            payload["telemetry"] = self.telemetry
        return payload


def write_json_report(summary: RunSummary, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = summary.to_dict()
    path.write_text(
        __import__("json").dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def format_console(summary: RunSummary) -> str:
    lines = [
        f"Scenario: {summary.scenario} (version {summary.version})",
        f"Started : {summary.started_at.astimezone(UTC).isoformat()}",
        f"Finished: {summary.finished_at.astimezone(UTC).isoformat()}",
        f"Status  : {'PASS' if summary.success else 'FAIL'}",
        "",
        "Stages:",
    ]
    for stage in summary.stages:
        status = "✅" if stage.success else "❌"
        detail = f" — {stage.detail}" if stage.detail else ""
        lines.append(f"  {status} {stage.name} ({stage.latency_ms:.0f} ms){detail}")
    if summary.prompts:
        lines.append("")
        lines.append("Prompt validations:")
        for prompt in summary.prompts:
            status = "✅" if prompt.success else "❌"
            failures = f" — {', '.join(prompt.failures)}" if prompt.failures else ""
            judge_suffix = ""
            if prompt.judge_name and prompt.judge_score is not None:
                judge_suffix = f"; {prompt.judge_name}={prompt.judge_score:.2f}"
            elif prompt.judge_name:
                judge_suffix = f"; {prompt.judge_name}"
            lines.append(
                f"  {status} {prompt.prompt_id} [{prompt.mode}] ({prompt.latency_ms:.0f} ms{judge_suffix}){failures}"
            )
            if prompt.judge_explanation and not prompt.success:
                lines.append(f"      {prompt.judge_explanation}")
            if prompt.requires_sql:
                query = prompt.sql_queries[0] if prompt.sql_queries else "N/A"
                row_count = prompt.sql_row_count
                if row_count is None:
                    row_count = len(prompt.sql_table_results)
                lines.append(
                    f"      SQL rows={row_count} query={query[:80]}"
                )
                if prompt.sql_table_results:
                    preview = prompt.sql_table_results[0]
                    lines.append(f"      preview={preview}")
    if summary.telemetry:
        lines.append("")
        lines.append("Telemetry:")
        real_tools = summary.telemetry.get("real_tools") or {}
        if real_tools:
            lines.append(
                "  Real tools: requested={requested} verified={verified} signals={signals}".format(
                    requested=real_tools.get("requested", False),
                    verified=real_tools.get("verified", False),
                    signals=real_tools.get("signals_recorded", 0),
                )
            )
            lines.append(
                "    embeddings={embeddings} reranker_prompts={reranker}".format(
                    embeddings=real_tools.get("embedding_jobs", 0),
                    reranker=real_tools.get("reranker_prompts", 0),
                )
            )
        http_calls = summary.telemetry.get("http_calls") or {}
        if http_calls:
            lines.append(
                "  HTTP calls: total={total} avg={avg:.0f} ms".format(
                    total=http_calls.get("total_calls", 0),
                    avg=http_calls.get("avg_latency_ms", 0.0),
                )
            )
    return "\n".join(lines)


def render_and_print(summary: RunSummary) -> None:
    print(format_console(summary))


__all__ = [
    "PromptRunResult",
    "RunSummary",
    "StageResult",
    "render_and_print",
    "write_json_report",
]
