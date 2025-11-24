"""
Pytest configuration and fixtures
"""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import TestConfig
from app.db import create_tables, drop_tables, get_session, init_db
from app.main import create_api_app
from app.models.user import User
from app.utils.auth import UserContext


@pytest.fixture(scope="function")
def fastapi_app(tmp_path_factory):
    """FastAPI application configured with an isolated SQLite database."""

    db_dir = tmp_path_factory.mktemp("data")
    db_path = db_dir / f"user_service_{uuid4().hex}.db"

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

    # Mock _require_user_context which is what the endpoints actually use
    async def mock_require_user_context(request):
        """Mock _require_user_context that extracts user info from token"""
        from app.db import get_session

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token"
            )

        parts = auth_header.split(maxsplit=1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header"
            )

        token = parts[1]
        # Decode token to get user info
        try:
            secret = fastapi_app.state.config.JWT_SECRET_KEY
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            user_id = payload.get("user_id") or payload.get("sub")
            role = payload.get("role", "public")
            roles = payload.get("roles", [role])

            # Get user from app's database to get country_code
            session = get_session()
            try:
                user = session.query(User).filter_by(user_id=user_id).first()
                country_code = user.country_code if user else "USA"
            finally:
                session.close()

            return UserContext(
                user_id=user_id,
                roles=roles,
                country_code=country_code,
                username=payload.get("username"),
                email=payload.get("email"),
            )
        except jwt.InvalidTokenError as e:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
            ) from e

    # Patch _require_user_context which is what the endpoints actually use
    with (
        patch("app.api.users._require_user_context", side_effect=mock_require_user_context),
        TestClient(fastapi_app) as test_client,
    ):
        yield test_client


@pytest.fixture(scope="function")
def db_session(tmp_path_factory):
    """Provide a SQLAlchemy session for testing"""
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


@pytest.fixture(scope="function")
def sample_user(db_session, fastapi_app):
    """Create a sample user for testing - uses app's database for integration tests"""
    # For integration tests, use app's database; for unit tests, use db_session
    try:
        from app.db import get_session

        session = get_session()
        use_app_db = True
    except RuntimeError:
        # Database not initialized, use db_session fixture
        session = db_session
        use_app_db = False

    try:
        user = User(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            password_hash="hashed_password",
            role="public",
            status="active",
            country_code="USA",
            email_verified=True,
            date_created=datetime.now(UTC),
            date_modified=datetime.now(UTC),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        if use_app_db:
            session.close()


@pytest.fixture(scope="function")
def admin_user(db_session, fastapi_app):
    """Create an admin user for testing - uses app's database for integration tests"""
    # For integration tests, use app's database; for unit tests, use db_session
    try:
        from app.db import get_session

        session = get_session()
        use_app_db = True
    except RuntimeError:
        # Database not initialized, use db_session fixture
        session = db_session
        use_app_db = False

    try:
        user = User(
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            password_hash="hashed_password",
            role="admin",
            status="active",
            country_code="USA",
            email_verified=True,
            date_created=datetime.now(UTC),
            date_modified=datetime.now(UTC),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        if use_app_db:
            session.close()


@pytest.fixture
def generate_token(client):
    """Fixture to generate JWT tokens for testing"""

    secret = client.app.state.config.JWT_SECRET_KEY

    def _generate_token(user_id, role="public"):
        payload = {
            "sub": user_id,
            "user_id": user_id,
            "role": role,
            "roles": [role],
            "type": "access",
            "iat": int(datetime.now(UTC).timestamp()),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")
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
