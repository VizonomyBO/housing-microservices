from __future__ import annotations

import pytest

from .core.runner import EvalRunner
from .core.scenarios import ResolvedScenario
from .core.telemetry import citation_doc_ids


@pytest.fixture
def blocking_scenarios(resolved_scenarios: list[ResolvedScenario]) -> list[ResolvedScenario]:
    return [
        resolved
        for resolved in resolved_scenarios
        if resolved.scenario.turns and resolved.scenario.turns[0].response_mode == "blocking"
    ]


@pytest.fixture
def streaming_scenarios(resolved_scenarios: list[ResolvedScenario]) -> list[ResolvedScenario]:
    return [
        resolved
        for resolved in resolved_scenarios
        if resolved.scenario.turns and resolved.scenario.turns[0].response_mode == "stream"
    ]


@pytest.mark.eval
@pytest.mark.eval_api
@pytest.mark.requires_prod
def test_blocking_scenarios(blocking_scenarios: list[ResolvedScenario], eval_runner: EvalRunner) -> None:
    for resolved in blocking_scenarios:
        result = eval_runner.run(resolved)
        assert result.chat_result.status_code == 200
        assert result.chat_result.answer
        attached_ids = {doc.document_id for doc in resolved.documents}
        cited_ids = set(citation_doc_ids(result.chat_result))
        assert not cited_ids or cited_ids.issubset(attached_ids)
        assert all(metric.passed or metric.skipped for metric in result.metrics)


@pytest.mark.eval
@pytest.mark.eval_sse
@pytest.mark.eval_heavy
@pytest.mark.requires_prod
def test_streaming_scenarios(streaming_scenarios: list[ResolvedScenario], eval_runner: EvalRunner) -> None:
    for resolved in streaming_scenarios:
        result = eval_runner.run(resolved)
        assert result.chat_result.status_code == 200
        assert result.chat_result.answer
        assert all(metric.passed or metric.skipped for metric in result.metrics)
