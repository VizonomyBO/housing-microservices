from __future__ import annotations

import os
import pathlib
from typing import Iterable, List

import pytest

from .core.client import AgentApiClient
from .core.config import EvalConfig
from .core.judges import LLMJudge
from .core.metrics import MetricEvaluator
from .core.runner import EvalRunner
from .core.scenarios import Dataset, ResolvedScenario, load_dataset, resolve_scenario


DATASET_PATH = pathlib.Path(__file__).parent / "datasets" / "shared_mex_arg.yaml"
ROOT_DIR = pathlib.Path(__file__).resolve().parents[4]


def _load_env_defaults() -> None:
    """Load prod defaults from the repo .env.prod file and set prod URLs if templated."""
    env_path = ROOT_DIR / ".env.prod"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value
    # Normalize templated URLs that rely on compose vars to prod defaults.
    agent_url = os.environ.get("AGENT_BASE_URL")
    if not agent_url or "${" in agent_url:
        os.environ["AGENT_BASE_URL"] = "http://52.207.140.87:8000"
    auth_url = os.environ.get("AUTH_BASE_URL")
    if not auth_url or "${" in auth_url:
        os.environ["AUTH_BASE_URL"] = "http://52.207.140.87:5001"


def pytest_configure(config: pytest.Config) -> None:
    markers = [
        "eval: Agent API eval suite",
        "eval_api: blocking HTTP evals",
        "eval_sse: streaming evals",
        "eval_pyodide: tool-heavy evals",
        "eval_heavy: long-running evals",
        "requires_prod: relies on prod stack and credentials",
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)


_load_env_defaults()


@pytest.fixture(scope="session")
def eval_config() -> EvalConfig:
    cfg = EvalConfig.from_env()
    missing = []
    if not cfg.eval_user_email:
        missing.append("EVAL_USER_EMAIL")
    if not cfg.eval_user_password:
        missing.append("EVAL_USER_PASSWORD")
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        pytest.fail(f"Missing required env for evals: {', '.join(missing)}")
    return cfg


@pytest.fixture(scope="session")
def eval_dataset() -> Dataset:
    return load_dataset(DATASET_PATH)


@pytest.fixture(scope="session")
def agent_client(eval_config: EvalConfig) -> Iterable[AgentApiClient]:
    client = AgentApiClient(
        agent_base_url=eval_config.agent_base_url,
        auth_base_url=eval_config.auth_base_url,
    )
    tokens = client.login(eval_config.eval_user_email, eval_config.eval_user_password)
    if not eval_config.eval_user_id:
        eval_config.eval_user_id = tokens.user_id
    yield client
    client.close()


@pytest.fixture(scope="session")
def documents_index(agent_client: AgentApiClient, eval_dataset: Dataset) -> dict[str, dict]:
    payload = agent_client.list_documents(page_size=100)
    docs = {item.get("document_id"): item for item in payload.get("documents", [])}
    missing = [doc.document_id for doc in eval_dataset.documents if doc.document_id not in docs]
    if missing:
        pytest.skip(f"Required documents are missing or inactive: {missing}")
    return docs


@pytest.fixture(scope="session")
def resolved_scenarios(eval_dataset: Dataset) -> List[ResolvedScenario]:
    return [resolve_scenario(eval_dataset, scenario) for scenario in eval_dataset.scenarios]


@pytest.fixture(scope="session")
def llm_judge(eval_config: EvalConfig) -> LLMJudge | None:
    return LLMJudge(
        model=eval_config.openai_model,
        reasoning_effort=eval_config.reasoning_effort,
    )


@pytest.fixture(scope="session")
def metric_evaluator(llm_judge: LLMJudge | None) -> MetricEvaluator:
    return MetricEvaluator(judge=llm_judge)


@pytest.fixture(scope="session")
def artifact_dir() -> pathlib.Path:
    path = pathlib.Path(__file__).parent / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def eval_runner(
    agent_client: AgentApiClient,
    metric_evaluator: MetricEvaluator,
    artifact_dir: pathlib.Path,
) -> EvalRunner:
    return EvalRunner(
        client=agent_client,
        metrics=metric_evaluator,
        artifact_dir=artifact_dir,
    )
