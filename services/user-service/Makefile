.PHONY: help install install-dev test test-unit test-integration test-coverage lint format format-check type-check clean run

help:
	@echo "Available commands:"
	@echo "  install          Install production dependencies"
	@echo "  install-dev      Install development dependencies"
	@echo "  test             Run all tests"
	@echo "  test-unit        Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-coverage    Run tests with coverage report"
	@echo "  lint             Run linting checks (ruff)"
	@echo "  format           Format code with ruff"
	@echo "  format-check     Check code formatting without modifying"
	@echo "  type-check       Run type checking with mypy"
	@echo "  clean            Clean up temporary files and caches"
	@echo "  run              Run the development server"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements/dev.txt
	pip install -r requirements/test.txt

test:
	pytest

test-unit:
	pytest -m unit

test-integration:
	pytest -m integration

test-coverage:
	pytest --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml

lint:
	python -m ruff check .

format:
	python -m ruff format .
	python -m ruff check --fix .

format-check:
	python -m ruff format --check .
	python -m ruff check .

type-check:
	mypy app

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

run:
	python run.py

# Quality check - run all checks
quality: format-check lint type-check
	@echo "All quality checks passed!"
