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
	docker-compose logs -f auth-service

logs-swagger: ## View logs from swagger service
	docker-compose logs -f swagger-service

logs-user: ## View logs from user service
	docker-compose logs -f user-service

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
	cd services/auth-service && python run.py

dev-swagger: ## Run swagger service in development mode (local)
	cd services/swagger-service && npm run dev

dev-user: ## Run user service in development mode (local)
	cd services/user-service && python run.py

install-account: ## Install account service dependencies (local)
	cd services/auth-service && pip install -r requirements.txt

install-swagger: ## Install swagger service dependencies (local)
	cd services/swagger-service && npm install

install-user: ## Install user service dependencies (local)
	cd services/user-service && pip install -r requirements.txt

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

test: test-account test-swagger test-user ## Run all tests locally

test-account: ## Run account service tests locally
	@if [ ! -d "services/auth-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pytest tests/ -v; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pytest tests/ -v; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi

test-swagger: ## Run swagger service tests locally
	cd services/swagger-service && npm test

test-user: ## Run user service tests locally
	@if [ ! -d "services/user-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-user-dev' first."; \
		exit 1; \
	fi
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pytest tests/ -v; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pytest tests/ -v; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi

test-account-unit: ## Run account service unit tests only
	@if [ ! -d "services/auth-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pytest tests/unit/ -v -m unit; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pytest tests/unit/ -v -m unit; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi

test-account-integration: ## Run account service integration tests only
	@if [ ! -d "services/auth-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pytest tests/integration/ -v -m integration; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pytest tests/integration/ -v -m integration; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi

test-user-unit: ## Run user service unit tests only
	@if [ ! -d "services/user-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-user-dev' first."; \
		exit 1; \
	fi
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pytest tests/unit/ -v -m unit; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pytest tests/unit/ -v -m unit; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi

test-user-integration: ## Run user service integration tests only
	@if [ ! -d "services/user-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-user-dev' first."; \
		exit 1; \
	fi
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pytest tests/integration/ -v -m integration; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pytest tests/integration/ -v -m integration; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi

test-coverage: ## Run tests with coverage reports
	@if [ ! -d "services/auth-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pytest tests/ --cov=app --cov-report=html --cov-report=term; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pytest tests/ --cov=app --cov-report=html --cov-report=term; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi
	cd services/swagger-service && npm run test:coverage
	@if [ -d "services/user-service/.venv" ]; then \
		cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pytest tests/ --cov=app --cov-report=html --cov-report=term; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pytest tests/ --cov=app --cov-report=html --cov-report=term; \
		fi; \
	fi
	@echo "\n==> Coverage reports generated:"
	@echo "    Account Service: services/auth-service/htmlcov/index.html"
	@echo "    User Service: services/user-service/htmlcov/index.html"
	@echo "    Swagger Service: services/swagger-service/coverage/lcov-report/index.html"

test-docker: ## Run tests in Docker containers
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from auth-service-test

test-docker-account: ## Run account service tests in Docker
	docker-compose -f docker-compose.test.yml up --build auth-service-test test-postgres --abort-on-container-exit

test-docker-swagger: ## Run swagger service tests in Docker
	docker-compose -f docker-compose.test.yml up --build swagger-service-test --abort-on-container-exit

# Linting commands
lint: lint-account lint-swagger lint-user ## Run all linting

lint-account: ## Lint account service
	@echo "==> Linting Account Service..."
	@if [ ! -d "services/auth-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			PYTHON_CMD=".venv/bin/python"; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			PYTHON_CMD=".venv/Scripts/python.exe"; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi && \
		$$PYTHON_CMD -m black --check app/ tests/ && \
		$$PYTHON_CMD -m flake8 app/ tests/ && \
		$$PYTHON_CMD -m mypy app/

lint-swagger: ## Lint swagger service
	@echo "==> Linting Swagger Service..."
	cd services/swagger-service && npm run lint
	cd services/swagger-service && npm run format:check

lint-user: ## Lint user service
	@echo "==> Linting User Service..."
	@if [ ! -d "services/user-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-user-dev' first."; \
		exit 1; \
	fi
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			PYTHON_CMD=".venv/bin/python"; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			PYTHON_CMD=".venv/Scripts/python.exe"; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi && \
		$$PYTHON_CMD -m black --check app/ tests/ && \
		$$PYTHON_CMD -m flake8 app/ tests/ && \
		$$PYTHON_CMD -m mypy app/

lint-fix: lint-fix-account lint-fix-swagger lint-fix-user ## Fix linting issues

lint-fix-account: ## Fix account service linting issues
	@if [ ! -d "services/auth-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			PYTHON_CMD=".venv/bin/python"; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			PYTHON_CMD=".venv/Scripts/python.exe"; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi && \
		$$PYTHON_CMD -m black app/ tests/ && \
		$$PYTHON_CMD -m isort app/ tests/

lint-fix-swagger: ## Fix swagger service linting issues
	cd services/swagger-service && npm run lint:fix
	cd services/swagger-service && npm run format

lint-fix-user: ## Fix user service linting issues
	@if [ ! -d "services/user-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-user-dev' first."; \
		exit 1; \
	fi
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			PYTHON_CMD=".venv/bin/python"; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			PYTHON_CMD=".venv/Scripts/python.exe"; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi && \
		$$PYTHON_CMD -m black app/ tests/ && \
		$$PYTHON_CMD -m isort app/ tests/

# Format code
format: ## Auto-format all code
	@echo "==> Formatting Account Service..."
	@if [ ! -d "services/auth-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			PYTHON_CMD=".venv/bin/python"; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			PYTHON_CMD=".venv/Scripts/python.exe"; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi && \
		$$PYTHON_CMD -m black app/ tests/ && \
		$$PYTHON_CMD -m isort app/ tests/
	@echo "==> Formatting Swagger Service..."
	cd services/swagger-service && npm run format
	@echo "==> Formatting User Service..."
	@if [ -d "services/user-service/.venv" ]; then \
		cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			PYTHON_CMD=".venv/bin/python"; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			PYTHON_CMD=".venv/Scripts/python.exe"; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi && \
		$$PYTHON_CMD -m black app/ tests/ && \
		$$PYTHON_CMD -m isort app/ tests/; \
	fi

# Type checking
type-check: ## Run type checking
	@echo "==> Type checking Account Service..."
	@if [ ! -d "services/auth-service/.venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-account-dev' first."; \
		exit 1; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m mypy app/; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m mypy app/; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi
	@echo "==> Type checking Swagger Service..."
	cd services/swagger-service && npm run type-check
	@echo "==> Type checking User Service..."
	@if [ -d "services/user-service/.venv" ]; then \
		cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m mypy app/; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m mypy app/; \
		fi; \
	fi

# Quality gates
quality: lint type-check test-coverage ## Run all quality checks

# Install dependencies
install-deps: install-account install-swagger ## Install all dependencies

install-account-dev: ## Install account service development dependencies
	@echo "==> Setting up Account Service virtual environment..."
	@if [ ! -d "services/auth-service/.venv" ]; then \
		cd services/auth-service && python -m venv .venv 2>/dev/null || python3 -m venv .venv; \
	fi
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install --upgrade pip; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install --upgrade pip; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi
	@echo "==> Installing base dependencies (excluding psycopg2-binary for now)..."
	@cd services/auth-service && \
		TMPFILE=$$(mktemp 2>/dev/null || echo ".base_no_pg.tmp") && \
		grep -v "psycopg2-binary" requirements/base.txt > $$TMPFILE && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install -r $$TMPFILE && \
			rm -f $$TMPFILE; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install -r $$TMPFILE && \
			rm -f $$TMPFILE; \
		fi
	@echo "==> Installing psycopg2-binary (requires PostgreSQL if building from source)..."
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install psycopg2-binary || \
			(echo "Warning: psycopg2-binary installation failed."; \
			 echo "This is OK for development/testing with SQLite."); \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install psycopg2-binary || \
			(echo "Warning: psycopg2-binary installation failed."; \
			 echo "This is OK for development/testing with SQLite."); \
		fi
	@echo "==> Installing dev dependencies..."
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install -r requirements/dev.txt || true; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install -r requirements/dev.txt || true; \
		fi
	@echo "==> Installing test dependencies..."
	@cd services/auth-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install -r requirements/test.txt || true; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install -r requirements/test.txt || true; \
		fi
	@echo "==> Account Service dependencies installed!"

install-swagger-dev: ## Install swagger service development dependencies
	cd services/swagger-service && npm install

install-user-dev: ## Install user service development dependencies
	@echo "==> Setting up User Service virtual environment..."
	@if [ ! -d "services/user-service/.venv" ]; then \
		cd services/user-service && python -m venv .venv 2>/dev/null || python3 -m venv .venv; \
	fi
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install --upgrade pip; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install --upgrade pip; \
		else \
			echo "Error: Could not find Python in virtual environment"; exit 1; \
		fi
	@echo "==> Installing base dependencies (excluding psycopg2-binary for now)..."
	@cd services/user-service && \
		TMPFILE=$$(mktemp 2>/dev/null || echo ".base_no_pg.tmp") && \
		grep -v "psycopg2-binary" requirements/base.txt > $$TMPFILE && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install -r $$TMPFILE && \
			rm -f $$TMPFILE; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install -r $$TMPFILE && \
			rm -f $$TMPFILE; \
		fi
	@echo "==> Installing psycopg2-binary (requires PostgreSQL if building from source)..."
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install psycopg2-binary || \
			(echo "Warning: psycopg2-binary installation failed."; \
			 echo "This is OK for development/testing with SQLite."); \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install psycopg2-binary || \
			(echo "Warning: psycopg2-binary installation failed."; \
			 echo "This is OK for development/testing with SQLite."); \
		fi
	@echo "==> Installing dev dependencies..."
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install -r requirements/dev.txt || true; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install -r requirements/dev.txt || true; \
		fi
	@echo "==> Installing test dependencies..."
	@cd services/user-service && \
		if [ -f ".venv/bin/python" ]; then \
			.venv/bin/python -m pip install -r requirements/test.txt || true; \
		elif [ -f ".venv/Scripts/python.exe" ]; then \
			.venv/Scripts/python.exe -m pip install -r requirements/test.txt || true; \
		fi
	@echo "==> User Service dependencies installed!"

# Clean test artifacts
clean-test: ## Clean test artifacts and coverage reports
	rm -rf services/auth-service/htmlcov
	rm -rf services/auth-service/.coverage
	rm -rf services/auth-service/.pytest_cache
	rm -rf services/user-service/htmlcov
	rm -rf services/user-service/.coverage
	rm -rf services/user-service/.pytest_cache
	rm -rf services/swagger-service/coverage
	rm -rf services/swagger-service/.jest_cache
	@echo "==> Test artifacts cleaned"

clean-all: clean clean-test ## Clean everything including test artifacts

