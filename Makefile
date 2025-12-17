UV ?= uv
PYTHON_VERSION ?= 3.13

UV_PROJECTS = services/agent-api services/ingestion-service packages/shared_data_layer
FLASK_PROJECTS = services/auth-service services/user-service

.PHONY: help sync format lint type-check test quality smoke-local clean

.DEFAULT_GOAL := help

help: ## Show available targets
	@echo "Quality gates for the text-only FastAPI/Flask stack (uv-first)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

sync: ## Create/refresh .venv and install deps for all services (uv-first)
	@set -e; \
	for dir in $(UV_PROJECTS); do \
		echo ">>> Syncing $$dir"; \
		(cd "$$dir" && $(UV) venv --python $(PYTHON_VERSION) .venv && $(UV) sync --all-extras); \
	done; \
	for dir in $(FLASK_PROJECTS); do \
		echo ">>> Syncing $$dir"; \
		(cd "$$dir" && $(UV) venv --python $(PYTHON_VERSION) .venv && \
			$(UV) pip sync -p .venv/bin/python requirements.txt && \
			$(UV) pip sync -p .venv/bin/python requirements/dev.txt && \
			$(UV) pip sync -p .venv/bin/python requirements/test.txt); \
	done

format: ## Run ruff format + autofix across services
	@set -e; \
	for dir in $(UV_PROJECTS); do \
		echo ">>> Formatting $$dir"; \
		(cd "$$dir" && $(UV) run ruff format . && $(UV) run ruff check --fix .); \
	done; \
	for dir in $(FLASK_PROJECTS); do \
		echo ">>> Formatting $$dir"; \
		PY_BIN=$$(cd "$$dir" && if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi); \
		(cd "$$dir" && $(UV) run --python "$$PY_BIN" ruff format . && $(UV) run --python "$$PY_BIN" ruff check --fix .); \
	done

lint: ## Run lint checks (ruff) across services
	@set -e; \
	for dir in $(UV_PROJECTS); do \
		echo ">>> Linting $$dir"; \
		(cd "$$dir" && $(UV) run ruff check .); \
	done; \
	for dir in $(FLASK_PROJECTS); do \
		echo ">>> Linting $$dir"; \
		PY_BIN=$$(cd "$$dir" && if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi); \
		(cd "$$dir" && $(UV) run --python "$$PY_BIN" ruff check .); \
	done

type-check: ## Run type checks (ty for uv projects, mypy for Flask services)
	@set -e; \
	for dir in $(UV_PROJECTS); do \
		echo ">>> Type checking $$dir"; \
		(cd "$$dir" && $(UV) run ty check .); \
	done; \
	for dir in $(FLASK_PROJECTS); do \
		echo ">>> Type checking $$dir"; \
		PY_BIN=$$(cd "$$dir" && if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi); \
		(cd "$$dir" && $(UV) run --python "$$PY_BIN" mypy app); \
	done

test: ## Run pytest across services (parallel where enabled)
	@set -e; \
	for dir in $(UV_PROJECTS); do \
		echo ">>> Testing $$dir"; \
		(cd "$$dir" && $(UV) run pytest -n auto); \
	done; \
	for dir in $(FLASK_PROJECTS); do \
		echo ">>> Testing $$dir"; \
		PY_BIN=$$(cd "$$dir" && if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi); \
		(cd "$$dir" && $(UV) run --python "$$PY_BIN" pytest -n auto); \
	done

quality: format lint type-check test ## Run full quality gate (format → lint → type → tests)

smoke-local: ## Run the lightweight smoke script against local stack (requires env + APIs)
	@set -e; \
	env_file=$$(scripts/use_env.sh local); \
	set -a && source "$$env_file" && set +a; \
	./test-api.sh

clean: ## Remove common caches and coverage artifacts
	@set -e; \
	find services packages -type d -name ".pytest_cache" -prune -exec rm -rf {} +; \
	find services packages -type d -name ".ruff_cache" -prune -exec rm -rf {} +; \
	find services packages -type f -name ".coverage" -delete; \
	find services packages -type d -name "htmlcov" -prune -exec rm -rf {} +
