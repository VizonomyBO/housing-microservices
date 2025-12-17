# User Service

User profile management microservice built with FastAPI.

## Features

- **User Profile Management**: Get and update user profiles
- **JWT Authentication**: Secure endpoints with JWT token validation
- **Role-Based Access Control**: Different permissions for admin and regular users
- **RESTful API**: Standard REST endpoints for user operations
- **Database Integration**: PostgreSQL with SQLAlchemy ORM

## API Endpoints

### Public Endpoints

- `GET /` - Service information
- `GET /health` - Health check

### Authenticated Endpoints

#### Current User
- `GET /users/me` - Get current user profile
- `PUT /users/me` - Update current user profile
- `PATCH /users/me` - Partially update current user profile

#### User Management (Authentication Required)
- `GET /users/<id>` - Get user by ID (own profile or admin only)

#### Admin Only
- `GET /users` - List all users with pagination and filtering
- `PUT /users/<id>` - Update user by ID
- `PATCH /users/<id>` - Partially update user by ID
- `DELETE /users/<id>` - Delete user by ID
- `GET /users/search` - Search users

## Setup

### Prerequisites

- Python 3.13+
- uv (recommended) or pip
- PostgreSQL

### Installation

1. Install dependencies with uv:
```bash
uv venv --python 3.13 .venv
export UV_PROJECT_ENV=.venv
uv pip install -r requirements.txt
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run the service:
```bash
uv run python run.py
```

The service will start on port 5001 by default.

## Docker

Build and run with Docker:

```bash
docker build -t user-service .
docker run -p 5001:5001 --env-file .env user-service
```

## Testing

Run tests with pytest:

```bash
# Install test dependencies (after setting UV_PROJECT_ENV)
uv pip install -r requirements/test.txt

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration
```

## Development

Install development dependencies:

```bash
uv pip install -r requirements/dev.txt
```

Format code with ruff:

```bash
uv run ruff format app tests
```

Check code with ruff:

```bash
uv run ruff check app tests
```

Type check with mypy:

```bash
uv run mypy app/
```

## Configuration

Configuration is managed through environment variables:

- `SECRET_KEY` - Flask secret key
- `DEBUG` - Enable debug mode (default: False)
- `PORT` - Service port (default: 5001)
- `AUTH_DATABASE_URL` - PostgreSQL connection string for auth_db
- `AUTH_SERVICE_URL` / `AUTH_INTERNAL_BASE_URL` - Base URL for auth-service validation
- `JWT_SECRET_KEY` - JWT signing key
- `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` - Token expiration time (default: 15)
- `CORS_ORIGINS` - Allowed CORS origins

## Architecture

```
user-service/
├── app/
│   ├── __init__.py          # Package init (legacy compatibility)
│   ├── main.py              # FastAPI application setup
│   ├── config.py            # Configuration
│   ├── api/                 # API endpoints
│   │   ├── users.py         # User management endpoints
│   │   └── system.py        # System endpoints
│   ├── models/              # Database models
│   │   └── user.py          # User model
│   ├── services/            # Business logic
│   │   └── user_service.py  # User service
│   └── utils/               # Utilities
│       ├── auth.py          # JWT authentication
│       └── validators.py    # Input validation
├── tests/                   # Test suite
│   ├── conftest.py          # Test fixtures
│   ├── unit/                # Unit tests
│   └── integration/         # Integration tests
├── requirements/            # Dependencies
├── Dockerfile               # Docker configuration
└── run.py                   # Application entry point
```

## Authentication

All protected endpoints require a valid JWT token in the Authorization header:

```
Authorization: Bearer <token>
```

The token must be issued by the auth-service and include:
- `sub`: User ID
- `role`: User role (public, admin, government, staff)

## User Model

Users have the following fields:

- `user_id` - Unique identifier
- `first_name` - First name
- `last_name` - Last name
- `email` - Email address (unique)
- `email_verified` - Email verification status
- `role` - User role (admin, public, government, staff)
- `status` - Account status (pending, active, inactive, suspended)
- `country_code` - ISO 3166-1 alpha-3 country code
- `date_created` - Account creation timestamp
- `date_modified` - Last modification timestamp
- `last_login` - Last login timestamp
- `notes` - Admin notes (sensitive field)

## License

Proprietary - All rights reserved
