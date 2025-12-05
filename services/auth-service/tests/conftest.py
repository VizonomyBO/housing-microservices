"""
Pytest configuration and shared fixtures for Auth Service tests (FastAPI).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.database import create_tables, drop_tables, get_session, init_db
from app.main import create_api_app
from tests.factories import RefreshTokenFactory, UserFactory
from tests.factories.base import clear_factory_session, set_factory_session


class TestConfig(Config):
    """Test configuration with secure defaults for testing."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
    }
    JWT_SECRET_KEY = "test-secret-key"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    SECRET_KEY = "test-secret"
    CORS_ORIGINS = ["*"]
    COOKIE_SECURE = False  # Disable secure cookies for testing (no HTTPS)
    APP_NAME = "Account Management Service"
    APP_VERSION = "1.0.0"
    SERVICE_NAME = "auth-service"
    SERVICE_VERSION = "1.0.0"


@pytest.fixture(scope="function")
def fastapi_app(tmp_path_factory):
    """FastAPI application configured with an isolated SQLite database."""
    db_dir = tmp_path_factory.mktemp("data")
    db_path = db_dir / f"auth_service_{uuid4().hex}.db"

    class FastAPITestConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {"check_same_thread": False},
        }

    app = create_api_app(FastAPITestConfig)
    yield app
    # Cleanup
    drop_tables()


@pytest.fixture(scope="function")
def client(fastapi_app):
    """FastAPI test client with startup/shutdown handling."""
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def db_session(tmp_path_factory):
    """
    Create a clean database session for each test.

    This fixture ensures complete test isolation by creating fresh
    tables before each test and cleaning up afterwards.
    """
    db_dir = tmp_path_factory.mktemp("data")
    db_path = db_dir / f"test_db_{uuid4().hex}.db"

    class TestDbConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {"check_same_thread": False},
        }

    config = TestDbConfig()
    init_db(config)
    create_tables()

    session = get_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        drop_tables()


# --- User Fixtures ---


@pytest.fixture
def sample_user(db_session):
    """Create a sample active user for testing."""
    set_factory_session(db_session)
    try:
        return UserFactory.create()
    finally:
        clear_factory_session()


@pytest.fixture
def verified_user(db_session):
    """Create a verified user for testing."""
    set_factory_session(db_session)
    try:
        return UserFactory.create(email_verified=True)
    finally:
        clear_factory_session()


@pytest.fixture
def inactive_user(db_session):
    """Create an inactive user for testing."""
    set_factory_session(db_session)
    try:
        return UserFactory.create_inactive()
    finally:
        clear_factory_session()


@pytest.fixture
def suspended_user(db_session):
    """Create a suspended user for testing."""
    set_factory_session(db_session)
    try:
        return UserFactory.create_suspended()
    finally:
        clear_factory_session()


@pytest.fixture
def pending_user(db_session):
    """Create a pending user for testing."""
    set_factory_session(db_session)
    try:
        return UserFactory.create_pending()
    finally:
        clear_factory_session()


# --- Authentication Fixtures ---


@pytest.fixture
def generate_token(client):
    """Fixture to generate JWT tokens for testing"""
    secret = client.app.state.config.JWT_SECRET_KEY

    def _generate_token(user_id, role="public", email=None, username=None):
        user_id_str = str(user_id)
        payload = {
            "user_id": user_id_str,
            "email": email or f"user{user_id_str}@example.com",
            "username": username or f"user{user_id_str}",
            "role": role,
            "roles": [role],
            "type": "access",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")
        return token

    return _generate_token


@pytest.fixture
def auth_headers(generate_token, sample_user):
    """
    Generate authentication headers with a valid access token.

    Returns headers dict suitable for authenticated API requests.
    """
    access_token = generate_token(
        sample_user.user_id,
        sample_user.role,
        email=sample_user.email,
        username=sample_user.username,
    )
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


@pytest.fixture
def auth_client(client, auth_headers):
    """
    Create a test client with pre-configured authentication headers.

    This fixture provides a convenient way to make authenticated requests.
    Note: FastAPI TestClient handles headers differently than Flask.
    """
    # For FastAPI, we pass headers directly in requests
    # This fixture is kept for compatibility but headers should be passed explicitly
    return client


# --- Token Fixtures ---


@pytest.fixture
def refresh_token_obj(db_session, sample_user):
    """Create a valid refresh token for testing."""
    set_factory_session(db_session)
    try:
        return RefreshTokenFactory.create(user=sample_user)
    finally:
        clear_factory_session()


@pytest.fixture
def expired_refresh_token(db_session, sample_user):
    """Create an expired refresh token for testing."""
    set_factory_session(db_session)
    try:
        return RefreshTokenFactory.create_expired(user=sample_user)
    finally:
        clear_factory_session()


@pytest.fixture
def revoked_refresh_token(db_session, sample_user):
    """Create a revoked refresh token for testing."""
    set_factory_session(db_session)
    try:
        return RefreshTokenFactory.create_revoked(user=sample_user)
    finally:
        clear_factory_session()
