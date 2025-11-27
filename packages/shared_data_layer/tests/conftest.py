import pytest

from shared_data_layer.testing.conftest import *  # noqa: F403


def pytest_addoption(parser):
    parser.addoption(
        "--end-to-end",
        action="store_true",
        default=False,
        help="Run the slow ingestion smoke tests that exercise the full stack.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "end_to_end: mark tests that exercise the ingestion-to-knowledge-graph flow "
        "and require --end-to-end to run.",
    )


def pytest_runtest_setup(item):
    if "end_to_end" in item.keywords and not item.config.getoption("--end-to-end"):
        pytest.skip("pass --end-to-end to execute ingestion smoke tests")
