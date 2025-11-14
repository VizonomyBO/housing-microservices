"""
Pytest configuration and fixtures
"""
import pytest
from datetime import datetime
from unittest.mock import patch
import jwt

from app import create_app, db
from app.config import TestConfig
from app.models.user import User


@pytest.fixture(scope="function")
def app():
    """Create application for testing"""
    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app):
    """Create database session for testing"""
    with app.app_context():
        yield db.session


@pytest.fixture(scope="function")
def sample_user(db_session):
    """Create a sample user for testing"""
    user = User(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        password_hash="hashed_password",
        role="public",
        status="active",
        country_code="USA",
        email_verified=True,
        date_created=datetime.utcnow(),
        date_modified=datetime.utcnow(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture(scope="function")
def admin_user(db_session):
    """Create an admin user for testing"""
    user = User(
        first_name="Admin",
        last_name="User",
        email="admin@example.com",
        password_hash="hashed_password",
        role="admin",
        status="active",
        country_code="USA",
        email_verified=True,
        date_created=datetime.utcnow(),
        date_modified=datetime.utcnow(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def generate_token(app):
    """Fixture to generate JWT tokens for testing"""

    def _generate_token(user_id, role="public"):
        with app.app_context():
            payload = {"sub": user_id, "role": role, "iat": datetime.utcnow()}
            token = jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")
            return token

    return _generate_token


@pytest.fixture
def auth_headers(generate_token, sample_user):
    """Fixture to generate authentication headers"""
    token = generate_token(sample_user.user_id, sample_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers(generate_token, admin_user):
    """Fixture to generate admin authentication headers"""
    token = generate_token(admin_user.user_id, admin_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_auth_service(app, sample_user, admin_user):
    """Fixture to mock auth service token verification"""

    def mock_verify(token):
        """Mock verify_token_with_auth_service"""
        # Decode token to get user info (for testing)
        try:
            with app.app_context():
                # Decode the JWT token
                payload = jwt.decode(token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
                user_id = payload.get("sub")

                # Return appropriate user data based on user_id
                if user_id == sample_user.user_id:
                    return {
                        "sub": sample_user.user_id,
                        "user_id": sample_user.user_id,
                        "username": sample_user.username,
                        "email": sample_user.email,
                        "role": sample_user.role,
                    }, None
                elif user_id == admin_user.user_id:
                    return {
                        "sub": admin_user.user_id,
                        "user_id": admin_user.user_id,
                        "username": admin_user.username,
                        "email": admin_user.email,
                        "role": admin_user.role,
                    }, None
                else:
                    return None, "Invalid token"
        except jwt.InvalidTokenError:
            return None, "Invalid token"
        except Exception:
            return None, "Invalid token"

    with patch("app.utils.auth.verify_token_with_auth_service", side_effect=mock_verify):
        yield
