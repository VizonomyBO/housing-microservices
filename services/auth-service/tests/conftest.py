"""
Pytest configuration and shared fixtures for Account Service tests
"""

from datetime import datetime, timedelta

import pytest

from app import create_app, db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.security import hash_password


class TestConfig:
    """Test configuration"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = "test-secret-key"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    SECRET_KEY = "test-secret"
    CORS_ORIGINS = ["*"]
    RATELIMIT_ENABLED = False
    COOKIE_SECURE = False  # Disable secure cookies for testing (no HTTPS)


@pytest.fixture(scope="session")
def app():
    """Create and configure a test Flask application"""
    test_app = create_app(TestConfig)

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """Create a test client"""
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app):
    """Create a clean database session for each test"""
    with app.app_context():
        # Create all tables
        db.create_all()

        yield db.session

        # Clean up after each test
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(db_session):
    """Create a sample user for testing"""
    user = User(
        email="test@example.com",
        password_hash=hash_password("TestPass123!"),
        first_name="Test",
        last_name="User",
        status="active",
        email_verified=False,
        country_code="USA",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def verified_user(db_session):
    """Create a verified user for testing"""
    user = User(
        email="verified@example.com",
        password_hash=hash_password("VerifiedPass123!"),
        first_name="Verified",
        last_name="User",
        status="active",
        email_verified=True,
        country_code="USA",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def inactive_user(db_session):
    """Create an inactive user for testing"""
    user = User(
        email="inactive@example.com",
        password_hash=hash_password("InactivePass123!"),
        first_name="Inactive",
        last_name="User",
        status="inactive",
        email_verified=False,
        country_code="USA",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def auth_headers(client, sample_user):
    """Generate authentication headers with valid access token"""
    from app.services.auth_service import AuthService

    access_token = AuthService.generate_access_token(sample_user)
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


@pytest.fixture
def refresh_token_obj(db_session, sample_user):
    """Create a refresh token for testing"""
    token_string = "test_refresh_token"
    refresh_token = RefreshToken(
        user_id=sample_user.id,
        token=token_string,
        expires_at=datetime.utcnow() + timedelta(days=30),
        user_agent="Test User Agent",
        ip_address="127.0.0.1",
    )
    db_session.add(refresh_token)
    db_session.commit()
    return refresh_token
