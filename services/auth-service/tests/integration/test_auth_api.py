"""
Integration tests for authentication API endpoints
"""

import json

import pytest


@pytest.mark.integration
class TestRegisterEndpoint:
    """Tests for /auth/register endpoint"""

    def test_register_success(self, client, db_session):
        """Test successful user registration"""
        response = client.post(
            "/auth/register",
            data=json.dumps(
                {
                    "email": "newuser@example.com",
                    "username": "newuser",
                    "password": "NewPass123!",
                    "first_name": "New",
                    "last_name": "User",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert "user" in data
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["username"] == "newuser"
        assert "password" not in data["user"]

    def test_register_without_optional_fields(self, client, db_session):
        """Test registration without optional fields"""
        response = client.post(
            "/auth/register",
            data=json.dumps(
                {
                    "email": "minimal@example.com",
                    "username": "minimaluser",
                    "password": "MinPass123!",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 201

    def test_register_with_invalid_email(self, client):
        """Test registration with invalid email"""
        response = client.post(
            "/auth/register",
            data=json.dumps(
                {"email": "invalid-email", "username": "testuser", "password": "TestPass123!"}
            ),
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_register_with_duplicate_email(self, client, sample_user):
        """Test registration with duplicate email"""
        response = client.post(
            "/auth/register",
            data=json.dumps(
                {
                    "email": sample_user.email,
                    "username": "differentuser",
                    "password": "TestPass123!",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "already registered" in data["error"].lower()

    def test_register_with_missing_fields(self, client):
        """Test registration with missing required fields"""
        response = client.post(
            "/auth/register",
            data=json.dumps(
                {
                    "email": "test@example.com"
                    # Missing username and password
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400


@pytest.mark.integration
class TestLoginEndpoint:
    """Tests for /auth/login endpoint"""

    def test_login_with_email_success(self, client, sample_user):
        """Test successful login with email"""
        response = client.post(
            "/auth/login",
            data=json.dumps({"login": "test@example.com", "password": "TestPass123!"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data

    def test_login_with_username_success(self, client, sample_user):
        """Test successful login with username"""
        response = client.post(
            "/auth/login",
            data=json.dumps({"login": "testuser", "password": "TestPass123!"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert "access_token" in data

    def test_login_with_wrong_password(self, client, sample_user):
        """Test login with incorrect password"""
        response = client.post(
            "/auth/login",
            data=json.dumps({"login": "test@example.com", "password": "WrongPassword!"}),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_login_with_nonexistent_user(self, client):
        """Test login with non-existent user"""
        response = client.post(
            "/auth/login",
            data=json.dumps({"login": "nonexistent@example.com", "password": "Password123!"}),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_login_with_inactive_user(self, client, inactive_user):
        """Test login with inactive user"""
        response = client.post(
            "/auth/login",
            data=json.dumps({"login": "inactive@example.com", "password": "InactivePass123!"}),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_login_with_missing_fields(self, client):
        """Test login with missing fields"""
        response = client.post(
            "/auth/login",
            data=json.dumps(
                {
                    "login": "test@example.com"
                    # Missing password
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400


@pytest.mark.integration
class TestRefreshEndpoint:
    """Tests for /auth/refresh endpoint"""

    def test_refresh_token_success(self, client, app, db_session, sample_user):
        """Test successful token refresh"""
        with app.app_context():
            # First login to get tokens
            login_response = client.post(
                "/auth/login",
                data=json.dumps({"login": "test@example.com", "password": "TestPass123!"}),
                content_type="application/json",
            )

            refresh_token = json.loads(login_response.data)["refresh_token"]

            # Refresh the token
            response = client.post(
                "/auth/refresh",
                data=json.dumps({"refresh_token": refresh_token}),
                content_type="application/json",
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["refresh_token"] != refresh_token  # Should be a new token

    def test_refresh_with_invalid_token(self, client):
        """Test refresh with invalid token"""
        response = client.post(
            "/auth/refresh",
            data=json.dumps({"refresh_token": "invalid_token"}),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_refresh_with_missing_token(self, client):
        """Test refresh with missing token"""
        response = client.post(
            "/auth/refresh", data=json.dumps({}), content_type="application/json"
        )

        assert response.status_code == 400


@pytest.mark.integration
class TestLogoutEndpoint:
    """Tests for /auth/logout endpoint"""

    def test_logout_success(self, client, app, db_session, sample_user):
        """Test successful logout"""
        with app.app_context():
            # Login first
            login_response = client.post(
                "/auth/login",
                data=json.dumps({"login": "test@example.com", "password": "TestPass123!"}),
                content_type="application/json",
            )

            refresh_token = json.loads(login_response.data)["refresh_token"]

            # Logout
            response = client.post(
                "/auth/logout",
                data=json.dumps({"refresh_token": refresh_token}),
                content_type="application/json",
            )

            assert response.status_code == 200

            # Try to use the token - should fail
            refresh_response = client.post(
                "/auth/refresh",
                data=json.dumps({"refresh_token": refresh_token}),
                content_type="application/json",
            )

            assert refresh_response.status_code == 401


@pytest.mark.integration
class TestProfileEndpoint:
    """Tests for /auth/profile endpoint"""

    def test_get_profile_with_valid_token(self, client, app, sample_user, auth_headers):
        """Test getting profile with valid token"""
        with app.app_context():
            response = client.get("/auth/profile", headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "user" in data
            assert data["user"]["email"] == sample_user.email

    def test_get_profile_without_token(self, client):
        """Test getting profile without token"""
        response = client.get("/auth/profile")

        assert response.status_code == 401

    def test_get_profile_with_invalid_token(self, client):
        """Test getting profile with invalid token"""
        response = client.get("/auth/profile", headers={"Authorization": "Bearer invalid_token"})

        assert response.status_code == 401


@pytest.mark.integration
class TestChangePasswordEndpoint:
    """Tests for /auth/change-password endpoint"""

    def test_change_password_success(self, client, app, sample_user, auth_headers):
        """Test successful password change"""
        with app.app_context():
            response = client.post(
                "/auth/change-password",
                data=json.dumps(
                    {"current_password": "TestPass123!", "new_password": "NewPassword123!"}
                ),
                headers=auth_headers,
                content_type="application/json",
            )

            assert response.status_code == 200

            # Verify can login with new password
            login_response = client.post(
                "/auth/login",
                data=json.dumps({"login": "test@example.com", "password": "NewPassword123!"}),
                content_type="application/json",
            )

            assert login_response.status_code == 200

    def test_change_password_with_wrong_current_password(self, client, auth_headers):
        """Test password change with wrong current password"""
        response = client.post(
            "/auth/change-password",
            data=json.dumps(
                {"current_password": "WrongPassword!", "new_password": "NewPassword123!"}
            ),
            headers=auth_headers,
            content_type="application/json",
        )

        assert response.status_code in [400, 401]

    def test_change_password_with_weak_new_password(self, client, auth_headers):
        """Test password change with weak new password"""
        response = client.post(
            "/auth/change-password",
            data=json.dumps({"current_password": "TestPass123!", "new_password": "weak"}),
            headers=auth_headers,
            content_type="application/json",
        )

        assert response.status_code == 400
