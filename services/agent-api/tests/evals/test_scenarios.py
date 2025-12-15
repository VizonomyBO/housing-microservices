from __future__ import annotations

import pytest

from .core.runner import EvalRunner
from .core.scenarios import EvalScenario, load_scenarios

pytestmark = pytest.mark.eval


SCENARIO_PATHS = [
    "datasets/housing_basics.yaml",
    "datasets/reduced_e2e_smoke.yaml",
]


def _load_all_scenarios() -> list[EvalScenario]:
    scenarios: list[EvalScenario] = []
    for path in SCENARIO_PATHS:
        scenarios.extend(load_scenarios(path))
    return scenarios


@pytest.mark.parametrize("scenario", _load_all_scenarios(), ids=lambda s: s.name)
def test_eval_scenario_smoke(scenario) -> None:
    runner = EvalRunner()
    result = runner.run(scenario, use_local_judge=True)
    result.assert_thresholds()
    artifact_path = result.write_artifacts()
    assert artifact_path.exists(), "artifact path missing"
