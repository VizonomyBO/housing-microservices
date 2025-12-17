UV ?= uv
PYTHON_VERSION ?= 3.13
VENV ?= .venv
PYTHON := $(VENV)/bin/python

.PHONY: help venv format lint type-check test quality clean run

.DEFAULT_GOAL := help

help: ## Show service commands
	@echo "Auth service quality gates (uv-first, text-only stack)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

venv: ## Create/refresh the uv-managed virtualenv with dev/test deps
	$(UV) venv --python $(PYTHON_VERSION) $(VENV)
	$(UV) pip sync -p $(PYTHON) requirements.txt
	$(UV) pip sync -p $(PYTHON) requirements/dev.txt
	$(UV) pip sync -p $(PYTHON) requirements/test.txt

format: venv ## Apply ruff formatting + autofix
	$(UV) run --python $(PYTHON) ruff format .
	$(UV) run --python $(PYTHON) ruff check --fix .

lint: venv ## Lint with ruff (no formatting)
	$(UV) run --python $(PYTHON) ruff check .

type-check: venv ## Type check with mypy
	$(UV) run --python $(PYTHON) mypy app

test: venv ## Run pytest (parallel where supported)
	$(UV) run --python $(PYTHON) pytest -n auto

quality: format lint type-check test ## Full quality gate

clean: ## Drop caches and coverage artifacts
	find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete

run: venv ## Run the development server
	$(UV) run --python $(PYTHON) python run.py
