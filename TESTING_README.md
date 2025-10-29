# Testing and Quality Assurance Guide

This guide covers testing, linting, and quality assurance practices for the microservices platform.

## Table of Contents

- [Quick Start](#quick-start)
- [Running Tests](#running-tests)
- [Code Quality](#code-quality)
- [Coverage Reports](#coverage-reports)
- [Docker Testing](#docker-testing)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Continuous Integration](#continuous-integration)

## Quick Start

### Install Dependencies

```bash
# Install all dependencies (production + development)
make install-deps

# Install development dependencies only
make install-account-dev
make install-swagger-dev
```

### Run All Tests

```bash
# Run all tests locally
make test

# Run tests with coverage
make test-coverage

# Run tests in Docker
make test-docker
```

### Run Linting

```bash
# Run all linting
make lint

# Fix linting issues automatically
make lint-fix

# Format all code
make format
```

## Running Tests

### Account Service (Python/Flask)

**Unit Tests:**
```bash
cd services/account-service
pytest tests/unit/ -v -m unit
```

**Integration Tests:**
```bash
cd services/account-service
pytest tests/integration/ -v -m integration
```

**All Tests:**
```bash
cd services/account-service
pytest tests/ -v
```

**With Coverage:**
```bash
cd services/account-service
pytest tests/ --cov=app --cov-report=html --cov-report=term
```

**Test Specific File:**
```bash
cd services/account-service
pytest tests/unit/test_auth_service.py -v
```

### Swagger Service (TypeScript/Node.js)

**All Tests:**
```bash
cd services/swagger-service
npm test
```

**Watch Mode:**
```bash
cd services/swagger-service
npm run test:watch
```

**With Coverage:**
```bash
cd services/swagger-service
npm run test:coverage
```

**Verbose Output:**
```bash
cd services/swagger-service
npm run test:verbose
```

**Test Specific File:**
```bash
cd services/swagger-service
npm test -- ServiceDiscovery.test.ts
```

## Code Quality

### Linting

#### Account Service (Python)

**Check Code:**
```bash
cd services/account-service

# Black - code formatting
black --check app/ tests/

# Flake8 - style guide enforcement
flake8 app/ tests/

# MyPy - type checking
mypy app/

# iSort - import sorting
isort --check-only app/ tests/

# Bandit - security linting
bandit -r app/
```

**Auto-fix:**
```bash
cd services/account-service

# Format code
black app/ tests/

# Sort imports
isort app/ tests/
```

#### Swagger Service (TypeScript)

**Check Code:**
```bash
cd services/swagger-service

# ESLint - linting
npm run lint

# Prettier - formatting check
npm run format:check

# TypeScript - type checking
npm run type-check
```

**Auto-fix:**
```bash
cd services/swagger-service

# Fix linting issues
npm run lint:fix

# Format code
npm run format
```

### Using Makefile Commands

```bash
# Check linting for all services
make lint

# Fix linting issues
make lint-fix

# Format all code
make format

# Run type checking
make type-check

# Run all quality checks (lint + type-check + test-coverage)
make quality
```

## Coverage Reports

### Viewing Coverage Reports

After running tests with coverage:

**Account Service:**
```bash
# HTML report
open services/account-service/htmlcov/index.html

# Terminal report
cd services/account-service
pytest tests/ --cov=app --cov-report=term-missing
```

**Swagger Service:**
```bash
# HTML report
open services/swagger-service/coverage/lcov-report/index.html

# Terminal report
cd services/swagger-service
npm run test:coverage
```

### Coverage Thresholds

Both services maintain **85% minimum coverage**:

- **Account Service:** Configured in `pytest.ini` and `pyproject.toml`
- **Swagger Service:** Configured in `jest.config.js`

Critical paths (authentication, security) maintain **95% coverage**.

## Docker Testing

### Run Tests in Docker Containers

**All Services:**
```bash
make test-docker
```

**Account Service Only:**
```bash
make test-docker-account
```

**Swagger Service Only:**
```bash
make test-docker-swagger
```

**Manual Docker Compose:**
```bash
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

### Multi-Stage Docker Builds

Both services use multi-stage Dockerfiles:

1. **Test Stage:** Runs tests, linting, and quality checks
2. **Production Stage:** Creates optimized production image

```bash
# Build test stage only
docker build --target test -t account-service:test services/account-service/

# Build production stage (default)
docker build -t account-service:latest services/account-service/
```

## Pre-commit Hooks

### Installation

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install
```

### Usage

Pre-commit hooks run automatically on `git commit`. To run manually:

```bash
# Run on all files
pre-commit run --all-files

# Run on staged files only
pre-commit run

# Run specific hook
pre-commit run black --all-files
```

### Configured Hooks

- **Python:** black, isort, flake8, bandit
- **TypeScript:** prettier, eslint
- **General:** trailing-whitespace, end-of-file-fixer, check-yaml, detect-private-key
- **Docker:** hadolint

## Continuous Integration

### GitHub Actions Workflow

Create `.github/workflows/test.yml`:

```yaml
name: Test and Quality

on: [push, pull_request]

jobs:
  test-account-service:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test_password
          POSTGRES_USER: test_user
          POSTGRES_DB: test_account_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        cd services/account-service
        pip install -r requirements/test.txt -r requirements/dev.txt
    
    - name: Run linting
      run: |
        cd services/account-service
        black --check app/ tests/
        flake8 app/ tests/
        mypy app/
    
    - name: Run tests
      run: |
        cd services/account-service
        pytest --cov=app --cov-fail-under=85
      env:
        DATABASE_URL: postgresql://test_user:test_password@localhost:5432/test_account_db

  test-swagger-service:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Setup Node.js
      uses: actions/setup-node@v3
      with:
        node-version: '20'
    
    - name: Install dependencies
      run: |
        cd services/swagger-service
        npm ci
    
    - name: Run linting
      run: |
        cd services/swagger-service
        npm run lint
        npm run type-check
    
    - name: Run tests
      run: |
        cd services/swagger-service
        npm run test:coverage
```

## Test Organization

### Account Service Structure

```
services/account-service/tests/
├── conftest.py              # Pytest fixtures
├── unit/                    # Unit tests
│   ├── test_auth_service.py
│   ├── test_user_service.py
│   ├── test_models.py
│   ├── test_utils_security.py
│   └── test_utils_validators.py
└── integration/             # Integration tests
    └── test_auth_api.py
```

### Swagger Service Structure

```
services/swagger-service/tests/
├── setup.ts                 # Jest setup
├── unit/                    # Unit tests
│   └── services/
│       ├── ServiceDiscovery.test.ts
│       ├── SpecAggregator.test.ts
│       └── HealthMonitor.test.ts
└── integration/             # Integration tests
    └── app.test.ts
```

## Best Practices

### Writing Tests

1. **Follow AAA Pattern:** Arrange, Act, Assert
2. **One Assertion Per Test:** Keep tests focused
3. **Use Descriptive Names:** Test names should describe what they test
4. **Mock External Dependencies:** Don't rely on external services
5. **Test Edge Cases:** Include error conditions and boundary cases

### Code Quality

1. **Run Linting Before Commit:** Use pre-commit hooks
2. **Maintain Coverage:** Keep coverage above 85%
3. **Write Type Hints:** Use type annotations in Python
4. **Document Complex Logic:** Add comments for non-obvious code
5. **Keep Functions Small:** Follow single responsibility principle

### Performance

1. **Use Fixtures:** Reuse test setup with fixtures
2. **Parallel Testing:** Run independent tests in parallel
3. **Mock Heavy Operations:** Mock database calls, API requests
4. **Clean Up After Tests:** Use teardown to clean resources

## Troubleshooting

### Common Issues

**Import Errors:**
```bash
# Ensure you're in the correct directory
cd services/account-service
export PYTHONPATH=$PWD
pytest tests/
```

**Database Connection Issues:**
```bash
# Check database is running
docker-compose ps
docker-compose logs postgres
```

**Node Module Errors:**
```bash
# Clean and reinstall
cd services/swagger-service
rm -rf node_modules package-lock.json
npm install
```

**Coverage Not Generated:**
```bash
# Ensure coverage tools are installed
pip install pytest-cov coverage  # Python
npm install --save-dev jest ts-jest  # Node
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [Jest Documentation](https://jestjs.io/)
- [Black Code Style](https://black.readthedocs.io/)
- [ESLint Documentation](https://eslint.org/)
- [Pre-commit Documentation](https://pre-commit.com/)

## Support

For issues or questions:
1. Check the test output for error messages
2. Review this guide for best practices
3. Check the `TESTING_AND_LINTING_PLAN.md` for detailed architecture
4. Run `make help` to see all available commands

