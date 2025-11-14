.PHONY: help install install-dev run test test-unit test-integration coverage lint format clean

help:
	@echo "Available commands:"
	@echo "  make install          Install production dependencies"
	@echo "  make install-dev      Install development dependencies"
	@echo "  make run              Run the service"
	@echo "  make test             Run all tests"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make test-integration Run integration tests only"
	@echo "  make coverage         Run tests with coverage report"
	@echo "  make lint             Run linters"
	@echo "  make format           Format code with black"
	@echo "  make clean            Clean temporary files"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements/dev.txt

run:
	python run.py

test:
	pytest

test-unit:
	pytest -m unit

test-integration:
	pytest -m integration

coverage:
	pytest --cov=app --cov-report=html --cov-report=term-missing

lint:
	flake8 app/ tests/
	mypy app/

format:
	black app/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info

