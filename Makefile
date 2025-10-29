# Makefile for Microservices Platform

.PHONY: help build up down logs clean restart ps health test

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

build: ## Build all Docker containers
	docker-compose build

up: ## Start all services
	docker-compose up -d

down: ## Stop all services
	docker-compose down

logs: ## View logs from all services
	docker-compose logs -f

logs-account: ## View logs from account service
	docker-compose logs -f account-service

logs-swagger: ## View logs from swagger service
	docker-compose logs -f swagger-service

logs-db: ## View logs from database
	docker-compose logs -f postgres

clean: ## Stop all services and remove volumes
	docker-compose down -v

restart: ## Restart all services
	docker-compose restart

ps: ## Show running containers
	docker-compose ps

health: ## Check health of all services
	@echo "Checking Swagger Aggregator..."
	@curl -s http://localhost:3000/health | python -m json.tool || echo "Swagger service not responding"
	@echo ""
	@echo "Checking Account Service..."
	@curl -s http://localhost:5000/health | python -m json.tool || echo "Account service not responding"

status: ## Show detailed system status
	@curl -s http://localhost:3000/api/status | python -m json.tool

refresh: ## Force refresh all service specs
	@curl -s -X POST http://localhost:3000/api/refresh | python -m json.tool

dev-account: ## Run account service in development mode (local)
	cd services/account-service && python run.py

dev-swagger: ## Run swagger service in development mode (local)
	cd services/swagger-service && npm run dev

install-account: ## Install account service dependencies (local)
	cd services/account-service && pip install -r requirements.txt

install-swagger: ## Install swagger service dependencies (local)
	cd services/swagger-service && npm install

test-register: ## Test user registration
	@curl -X POST http://localhost:5000/auth/register \
		-H "Content-Type: application/json" \
		-d '{"email":"test@example.com","username":"testuser","password":"TestPass123!","first_name":"Test","last_name":"User"}' \
		| python -m json.tool

test-login: ## Test user login
	@curl -X POST http://localhost:5000/auth/login \
		-H "Content-Type: application/json" \
		-d '{"login":"test@example.com","password":"TestPass123!"}' \
		| python -m json.tool

open-docs: ## Open API documentation in browser
	@open http://localhost:3000/docs || xdg-open http://localhost:3000/docs || echo "Open http://localhost:3000/docs in your browser"

open-app: ## Open application landing page in browser
	@open http://localhost:3000 || xdg-open http://localhost:3000 || echo "Open http://localhost:3000 in your browser"

# ============================================
# Testing and Quality Commands
# ============================================

test: test-account test-swagger ## Run all tests locally

test-account: ## Run account service tests locally
	@if [ ! -d "services/account-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	cd services/account-service && .venv/bin/python -m pytest tests/ -v

test-swagger: ## Run swagger service tests locally
	cd services/swagger-service && npm test

test-account-unit: ## Run account service unit tests only
	@if [ ! -d "services/account-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	cd services/account-service && .venv/bin/python -m pytest tests/unit/ -v -m unit

test-account-integration: ## Run account service integration tests only
	@if [ ! -d "services/account-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	cd services/account-service && .venv/bin/python -m pytest tests/integration/ -v -m integration

test-coverage: ## Run tests with coverage reports
	@if [ ! -d "services/account-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	cd services/account-service && .venv/bin/python -m pytest tests/ --cov=app --cov-report=html --cov-report=term
	cd services/swagger-service && npm run test:coverage
	@echo "\n==> Coverage reports generated:"
	@echo "    Account Service: services/account-service/htmlcov/index.html"
	@echo "    Swagger Service: services/swagger-service/coverage/lcov-report/index.html"

test-docker: ## Run tests in Docker containers
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from account-service-test

test-docker-account: ## Run account service tests in Docker
	docker-compose -f docker-compose.test.yml up --build account-service-test test-postgres --abort-on-container-exit

test-docker-swagger: ## Run swagger service tests in Docker
	docker-compose -f docker-compose.test.yml up --build swagger-service-test --abort-on-container-exit

# Linting commands
lint: lint-account lint-swagger ## Run all linting

lint-account: ## Lint account service
	@echo "==> Linting Account Service..."
	@if [ ! -d "services/account-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	cd services/account-service && .venv/bin/python -m black --check app/ tests/
	cd services/account-service && .venv/bin/python -m flake8 app/ tests/
	cd services/account-service && .venv/bin/python -m mypy app/

lint-swagger: ## Lint swagger service
	@echo "==> Linting Swagger Service..."
	cd services/swagger-service && npm run lint
	cd services/swagger-service && npm run format:check

lint-fix: lint-fix-account lint-fix-swagger ## Fix linting issues

lint-fix-account: ## Fix account service linting issues
	@if [ ! -d "services/account-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	cd services/account-service && .venv/bin/python -m black app/ tests/
	cd services/account-service && .venv/bin/python -m isort app/ tests/

lint-fix-swagger: ## Fix swagger service linting issues
	cd services/swagger-service && npm run lint:fix
	cd services/swagger-service && npm run format

# Format code
format: ## Auto-format all code
	@echo "==> Formatting Account Service..."
	@if [ ! -d "services/account-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	cd services/account-service && .venv/bin/python -m black app/ tests/
	cd services/account-service && .venv/bin/python -m isort app/ tests/
	@echo "==> Formatting Swagger Service..."
	cd services/swagger-service && npm run format

# Type checking
type-check: ## Run type checking
	@echo "==> Type checking Account Service..."
	@if [ ! -d "services/account-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	cd services/account-service && .venv/bin/python -m mypy app/
	@echo "==> Type checking Swagger Service..."
	cd services/swagger-service && npm run type-check

# Quality gates
quality: lint type-check test-coverage ## Run all quality checks

# Install dependencies
install-deps: install-account install-swagger ## Install all dependencies

install-account-dev: ## Install account service development dependencies
	@echo "==> Setting up Account Service virtual environment..."
	@if [ ! -d "services/account-service/.venv" ]; then \
		cd services/account-service && python3 -m venv .venv; \
	fi
	cd services/account-service && .venv/bin/pip install --upgrade pip
	@echo "==> Installing base dependencies (excluding psycopg2-binary for now)..."
	@cd services/account-service && \
		grep -v "psycopg2-binary" requirements/base.txt > /tmp/base_no_pg.txt && \
		.venv/bin/pip install -r /tmp/base_no_pg.txt && \
		rm /tmp/base_no_pg.txt || true
	@echo "==> Installing psycopg2-binary (requires PostgreSQL if building from source)..."
	@cd services/account-service && .venv/bin/pip install psycopg2-binary || \
		(echo "Warning: psycopg2-binary installation failed."; \
		 echo "This is OK for development/testing with SQLite."; \
		 echo "To install PostgreSQL support, run: brew install postgresql"; \
		 echo "Then run: cd services/account-service && .venv/bin/pip install psycopg2-binary")
	@echo "==> Installing dev dependencies..."
	cd services/account-service && .venv/bin/pip install -r requirements/dev.txt || true
	@echo "==> Installing test dependencies..."
	cd services/account-service && .venv/bin/pip install -r requirements/test.txt || true
	@echo "==> Account Service dependencies installed!"

install-swagger-dev: ## Install swagger service development dependencies
	cd services/swagger-service && npm install

# Clean test artifacts
clean-test: ## Clean test artifacts and coverage reports
	rm -rf services/account-service/htmlcov
	rm -rf services/account-service/.coverage
	rm -rf services/account-service/.pytest_cache
	rm -rf services/swagger-service/coverage
	rm -rf services/swagger-service/.jest_cache
	@echo "==> Test artifacts cleaned"

clean-all: clean clean-test ## Clean everything including test artifacts

