# Testing Quick Reference Card

## ⚡ First Time Setup (IMPORTANT!)

Before running any tests or linting, you must install dependencies:

### Account Service (Python)
```bash
cd services/account-service

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies
pip install -r requirements/base.txt
pip install -r requirements/dev.txt
pip install -r requirements/test.txt
```

### Swagger Service (TypeScript)
```bash
cd services/swagger-service

# Install all dependencies
npm install
```

### Quick Install (Both Services)
```bash
# From project root
make install-account-dev
make install-swagger-dev
```

**Note:** Always activate the virtual environment before running Python commands:
```bash
cd services/account-service
source .venv/bin/activate
```

## 🚀 Quick Commands

### Run Tests
```bash
make test                    # All tests
make test-account           # Account service only
make test-swagger           # Swagger service only
make test-coverage          # With coverage reports
make test-docker            # In Docker containers
```

### Code Quality
```bash
make lint                   # Check all linting
make lint-fix              # Auto-fix issues
make format                # Format all code
make type-check            # Run type checking
make quality               # All quality checks
```

### Coverage Reports
```bash
# Account Service
open services/account-service/htmlcov/index.html

# Swagger Service
open services/swagger-service/coverage/lcov-report/index.html
```

### Clean Up
```bash
make clean-test            # Remove test artifacts
make clean-all             # Remove everything
```

## 📁 Test File Locations

### Account Service
```
services/account-service/tests/
├── conftest.py                     # Fixtures
├── unit/
│   ├── test_auth_service.py       # 15+ tests
│   ├── test_user_service.py       # 12+ tests
│   ├── test_models.py             # 15+ tests
│   ├── test_utils_security.py     # 12+ tests
│   └── test_utils_validators.py   # 18+ tests
└── integration/
    └── test_auth_api.py            # 20+ tests
```

### Swagger Service
```
services/swagger-service/tests/
├── setup.ts
├── unit/services/
│   ├── ServiceDiscovery.test.ts    # 25+ tests
│   ├── SpecAggregator.test.ts      # 15+ tests
│   └── HealthMonitor.test.ts       # 15+ tests
└── integration/
    └── app.test.ts                 # 5+ tests
```

## 🔧 Configuration Files

| Service | Testing | Linting | Format | Type Check |
|---------|---------|---------|--------|------------|
| Account | `pytest.ini` | `.flake8` | `pyproject.toml` | `pyproject.toml` |
| Swagger | `jest.config.js` | `.eslintrc.js` | `.prettierrc` | `tsconfig.json` |

## 🎯 Coverage Targets

- **Minimum**: 85% line coverage
- **Critical paths**: 95% (auth, security)
- **Reports**: HTML + Terminal + XML

## 🐳 Docker Commands

```bash
# Build test image
docker build --target test -t service:test services/account-service/

# Build production image
docker build --target production -t service:prod services/account-service/

# Run tests in Docker
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

## 🔍 Common Test Commands

### Account Service (Python)
```bash
cd services/account-service

# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v -m unit

# Integration tests only
pytest tests/integration/ -v -m integration

# Specific file
pytest tests/unit/test_auth_service.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html

# Watch mode (requires pytest-watch)
ptw -- tests/
```

### Swagger Service (TypeScript)
```bash
cd services/swagger-service

# All tests
npm test

# Watch mode
npm run test:watch

# Coverage
npm run test:coverage

# Specific file
npm test -- ServiceDiscovery.test.ts

# Verbose
npm run test:verbose
```

## 🎨 Linting Commands

### Account Service
```bash
cd services/account-service

# Check
black --check app/ tests/
flake8 app/ tests/
mypy app/
isort --check-only app/ tests/

# Fix
black app/ tests/
isort app/ tests/
```

### Swagger Service
```bash
cd services/swagger-service

# Check
npm run lint
npm run format:check
npm run type-check

# Fix
npm run lint:fix
npm run format
```

## 🪝 Pre-commit Hooks

```bash
# Install
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files

# Update hooks
pre-commit autoupdate

# Skip hooks (not recommended)
git commit --no-verify
```

## 📊 Understanding Test Output

### Pytest Markers
- `@pytest.mark.unit` - Unit test
- `@pytest.mark.integration` - Integration test
- `@pytest.mark.slow` - Slow running test
- `@pytest.mark.security` - Security test

### Jest Output
- ✓ Green check - Test passed
- ✕ Red cross - Test failed
- ○ Circle - Test skipped
- Coverage % - Shows coverage percentage

## 🚨 Troubleshooting

### Tests Failing?
```bash
# Check dependencies installed
make install-deps

# Clear caches
make clean-test

# Check database running
docker-compose ps
```

### Linting Errors?
```bash
# Auto-fix most issues
make lint-fix

# Format code
make format
```

### Import Errors?
```bash
# Python
export PYTHONPATH=$PWD
cd services/account-service

# Node
cd services/swagger-service
rm -rf node_modules && npm install
```

## 🎓 Test Writing Patterns

### Python (pytest)
```python
def test_feature_description(fixture):
    # Arrange
    data = setup_data()
    
    # Act
    result = function_to_test(data)
    
    # Assert
    assert result == expected
```

### TypeScript (Jest)
```typescript
describe('FeatureName', () => {
  it('should do something', () => {
    // Arrange
    const data = setupData();
    
    // Act
    const result = functionToTest(data);
    
    // Assert
    expect(result).toBe(expected);
  });
});
```

## 🔗 Useful Links

- Full Guide: `TESTING_README.md`
- Implementation: `TESTING_IMPLEMENTATION_SUMMARY.md`
- Plan: `TESTING_AND_LINTING_PLAN.md`
- Make Help: `make help`

## 💡 Pro Tips

1. **Run tests before committing** - `make test`
2. **Use pre-commit hooks** - They catch issues early
3. **Check coverage** - Aim for 85%+
4. **Watch mode for TDD** - Fast feedback loop
5. **Run linting regularly** - Don't let issues pile up
6. **Test one thing at a time** - Keep tests focused
7. **Use descriptive test names** - Make failures clear
8. **Mock external dependencies** - Tests should be fast
9. **Clean up after tests** - Use fixtures and teardown
10. **Review coverage reports** - Find untested code

## 📈 CI/CD Integration

```yaml
# Example GitHub Actions
- name: Run tests
  run: make test-coverage
  
- name: Check coverage
  run: |
    cd services/account-service
    pytest --cov=app --cov-fail-under=85
```

---

**Need more help?** Check `TESTING_README.md` or run `make help`

