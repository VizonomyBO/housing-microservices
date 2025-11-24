"""Authentication helper utilities for testing (FastAPI)."""

from fastapi.testclient import TestClient

from app.models.user import User
from app.services.auth_service import AuthService


def create_auth_headers(user: User) -> dict[str, str]:
    """
    Create authentication headers for a user.

    Args:
        user: User instance to create headers for

    Returns:
        Dictionary with Authorization header and access token
    """
    access_token = AuthService.generate_access_token(user)
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def login_user(
    client: TestClient,
    email: str,
    password: str,
) -> tuple[str, str, dict]:
    """
    Login a user and return tokens and user data.

    Args:
        client: FastAPI test client
        email: User email
        password: User password

    Returns:
        Tuple of (access_token, refresh_token, user_data)
    """
    response = client.post(
        "/v1/auth/login",
        json={"login": email, "password": password},
    )

    assert response.status_code == 200, f"Login failed: {response.json()}"

    data = response.json()
    return (
        data.get("access_token"),
        data.get("refresh_token"),
        data.get("user"),
    )


def register_user(
    client: TestClient,
    email: str,
    username: str,
    password: str,
    **kwargs,
) -> dict:
    """
    Register a new user.

    Args:
        client: FastAPI test client
        email: User email
        username: Username
        password: Password
        **kwargs: Additional user fields

    Returns:
        User data from registration response
    """
    payload = {
        "email": email,
        "username": username,
        "password": password,
        **kwargs,
    }

    response = client.post("/v1/auth/register", json=payload)

    assert response.status_code == 201, f"Registration failed: {response.json()}"

    data = response.json()
    return data.get("user", {})


def refresh_token(client: TestClient, refresh_token: str) -> tuple[str, str]:
    """
    Refresh access token using a refresh token.

    Args:
        client: FastAPI test client
        refresh_token: Valid refresh token

    Returns:
        Tuple of (new_access_token, new_refresh_token)
    """
    response = client.post(
        "/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200, f"Token refresh failed: {response.json()}"

    data = response.json()
    return data.get("access_token"), data.get("refresh_token")


def logout_user(client: TestClient, refresh_token: str) -> None:
    """
    Logout a user by revoking their refresh token.

    Args:
        client: FastAPI test client
        refresh_token: Refresh token to revoke
    """
    response = client.post(
        "/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200, f"Logout failed: {response.json()}"
