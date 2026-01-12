from __future__ import annotations

import os
import pathlib
from collections.abc import Iterable

import pytest
from fastapi.testclient import TestClient

from agent_api.http.app import create_app

from .core.client import AgentApiClient
from .core.config import EvalConfig
from .core.judges import LLMJudge
from .core.metrics import MetricEvaluator
from .core.runner import EvalRunner
from .core.scenarios import Dataset, ResolvedScenario, load_dataset, resolve_scenario

DATASET_PATH = pathlib.Path(__file__).parent / "datasets" / "shared_mex_arg.yaml"
ROOT_DIR = pathlib.Path(__file__).resolve().parents[4]
EVAL_ENV_FILE = ".env.evals"
PROD_ENV_FILE = ".env.prod"


def _load_env_defaults() -> None:
    """
    Load eval defaults from .env.evals only. Fail fast if missing to avoid implicit defaults.
    """

    env_path = ROOT_DIR / EVAL_ENV_FILE
    if not env_path.exists():
        msg = f"Missing {EVAL_ENV_FILE}; cannot load eval defaults."
        raise RuntimeError(msg)

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            expanded = os.path.expandvars(value)
            os.environ[key] = expanded


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
    if not cfg.auth_base_url:
        missing.append("AUTH_BASE_URL")
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
    # Run Agent API in-process via ASGI transport (no external HTTP for agent).
    app = create_app()
    with TestClient(app) as agent_tc:
        client = AgentApiClient(
            agent_base_url="http://testserver",
            auth_base_url=eval_config.auth_base_url,
            transport=None,
            agent_test_client=agent_tc,
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
def resolved_scenarios(eval_dataset: Dataset) -> list[ResolvedScenario]:
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


@pytest.fixture
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
