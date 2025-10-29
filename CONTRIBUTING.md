# Contributing Guidelines

Thank you for your interest in contributing to the Microservices Platform!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone <your-fork-url>`
3. Create a feature branch: `git checkout -b feature/amazing-feature`
4. Make your changes
5. Test your changes
6. Commit: `git commit -m 'Add amazing feature'`
7. Push: `git push origin feature/amazing-feature`
8. Open a Pull Request

## Development Setup

### Prerequisites

- Docker Desktop
- Python 3.11+ (for local development)
- Node.js 18+ (for local development)
- Git

### Local Development

#### Account Service

```bash
cd services/account-service
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://account_user:secure_password@localhost:5432/account_db
python run.py
```

#### Swagger Service

```bash
cd services/swagger-service
npm install
npm run dev
```

## Code Standards

### Python (Account Service)

- Follow PEP 8 style guide
- Use type hints where applicable
- Write docstrings for functions and classes
- Maximum line length: 100 characters
- Use meaningful variable names

**Example:**

```python
def create_user(email: str, username: str, password: str) -> tuple[User, str] | tuple[None, str]:
    """
    Create a new user with validation.
    
    Args:
        email: User email address
        username: User username
        password: User password (plain text)
        
    Returns:
        Tuple of (User object, None) on success or (None, error_message) on failure
    """
    # Implementation
    pass
```

### TypeScript (Swagger Service)

- Follow TypeScript best practices
- Use strict mode
- Define interfaces for all data structures
- Use async/await for asynchronous operations
- Export types for reusability

**Example:**

```typescript
export interface ServiceConfig {
  name: string;
  url: string;
  specEndpoint: string;
  healthEndpoint: string;
  description: string;
}

export async function fetchServiceSpec(service: ServiceConfig): Promise<OpenAPISpec | null> {
  try {
    const response = await axios.get(`${service.url}${service.specEndpoint}`);
    return response.data;
  } catch (error) {
    logger.error(`Failed to fetch spec: ${error}`);
    return null;
  }
}
```

## Testing

### Running Tests

```bash
# Test Account Service
cd services/account-service
pytest

# Test Swagger Service
cd services/swagger-service
npm test

# Integration tests
./test-api.sh
```

### Writing Tests

- Write unit tests for all business logic
- Write integration tests for API endpoints
- Aim for >80% code coverage
- Test edge cases and error conditions

## Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

**Examples:**

```
feat: add password reset email template
fix: resolve token expiration bug
docs: update API documentation
refactor: improve error handling in auth service
test: add unit tests for user validation
```

## Pull Request Process

1. **Update Documentation**: Update README.md or other docs if needed
2. **Add Tests**: Ensure new code has tests
3. **Run Tests**: All tests must pass
4. **Check Linting**: Code must pass linting checks
5. **Update Changelog**: Add entry to CHANGELOG.md if applicable
6. **Describe Changes**: Provide clear PR description

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests pass locally
- [ ] No new warnings
```

## Adding New Features

### Adding a New Microservice

1. Create service directory: `services/your-service/`
2. Implement OpenAPI spec endpoint: `/openapi.json`
3. Implement health check: `/health`
4. Create Dockerfile
5. Update `docker-compose.yml`
6. Register in Swagger service config
7. Update documentation

### Adding New Endpoints

**Account Service:**

1. Define endpoint in appropriate blueprint (`api/auth.py` or `api/system.py`)
2. Add validation logic
3. Implement service layer logic
4. Update OpenAPI spec in `api/system.py`
5. Add rate limiting if needed
6. Write tests

**Swagger Service:**

1. Add route in appropriate router
2. Implement handler function
3. Add TypeScript types
4. Update error handling
5. Write tests

## Code Review Guidelines

### For Authors

- Keep PRs focused and reasonably sized
- Respond to feedback promptly
- Be open to suggestions
- Update PR based on feedback

### For Reviewers

- Be respectful and constructive
- Focus on code quality and best practices
- Check for security issues
- Verify tests are adequate
- Approve when ready

## Security

### Reporting Security Issues

**DO NOT** open public issues for security vulnerabilities.

Email security concerns to: security@example.com

### Security Best Practices

- Never commit secrets or credentials
- Use environment variables for configuration
- Validate all user inputs
- Use parameterized queries
- Keep dependencies updated
- Follow OWASP guidelines

## Documentation

### Documentation Standards

- Use clear, concise language
- Include code examples
- Keep documentation up-to-date
- Add inline comments for complex logic
- Update API documentation when endpoints change

### Documentation Types

- **README.md**: Getting started, quick reference
- **ARCHITECTURE.md**: System design, technical details
- **QUICKSTART.md**: Fast setup guide
- **API Docs**: Generated from OpenAPI specs
- **Inline Comments**: Complex logic explanation

## Questions?

- Check existing documentation
- Search existing issues
- Ask in discussions
- Contact maintainers

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing! 🎉

