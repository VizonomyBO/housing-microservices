"""
Unit tests for authentication utilities
"""
import pytest
from unittest.mock import Mock, patch

from app.utils.auth import (
    get_token_from_header,
    verify_token_with_auth_service,
    token_required,
    admin_required,
)


@pytest.mark.unit
class TestAuthUtils:
    """Test authentication utility functions"""

    def test_get_token_from_header_valid(self, app):
        """Test extracting token from valid Authorization header"""
        with app.test_request_context(headers={"Authorization": "Bearer test_token_123"}):
            token = get_token_from_header()
            assert token == "test_token_123"

    def test_get_token_from_header_missing(self, app):
        """Test extracting token when Authorization header is missing"""
        with app.test_request_context():
            token = get_token_from_header()
            assert token is None

    def test_get_token_from_header_invalid_format(self, app):
        """Test extracting token from invalid format"""
        with app.test_request_context(headers={"Authorization": "InvalidFormat"}):
            token = get_token_from_header()
            assert token is None

        with app.test_request_context(headers={"Authorization": "Bearer"}):
            token = get_token_from_header()
            assert token is None

    def test_get_token_from_cookie_fallback(self, app):
        """Test extracting token from cookie when Authorization header is missing"""
        with app.test_request_context(cookies={"access_token": "cookie_token_123"}):
            token = get_token_from_header()
            assert token == "cookie_token_123"

    def test_get_token_from_body_fallback(self, app):
        """Test extracting token from request body when header and cookie are missing"""
        with app.test_request_context(
            method="POST",
            json={"token": "body_token_123"},
            content_type="application/json",
        ):
            token = get_token_from_header()
            assert token == "body_token_123"

    def test_get_token_from_body_access_token_key(self, app):
        """Test extracting token from request body using access_token key"""
        with app.test_request_context(
            method="POST",
            json={"access_token": "body_access_token_123"},
            content_type="application/json",
        ):
            token = get_token_from_header()
            assert token == "body_access_token_123"

    def test_get_token_priority_header_over_cookie(self, app):
        """Test that Authorization header takes priority over cookie"""
        with app.test_request_context(
            headers={"Authorization": "Bearer header_token"},
            cookies={"access_token": "cookie_token"},
        ):
            token = get_token_from_header()
            assert token == "header_token"

    def test_get_token_priority_cookie_over_body(self, app):
        """Test that cookie takes priority over request body"""
        with app.test_request_context(
            cookies={"access_token": "cookie_token"},
            method="POST",
            json={"token": "body_token"},
            content_type="application/json",
        ):
            token = get_token_from_header()
            assert token == "cookie_token"

    @patch("app.utils.auth.requests.post")
    def test_verify_token_valid(self, mock_post, app):
        """Test verifying valid token"""
        with app.app_context():
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "valid": True,
                "user_id": 1,
                "username": "john.doe",
                "email": "john@example.com",
                "role": "public",
            }
            mock_post.return_value = mock_response

            payload, error = verify_token_with_auth_service("valid_token")
            assert error is None
            assert payload["user_id"] == 1
            assert payload["email"] == "john@example.com"
            assert payload["role"] == "public"

    @patch("app.utils.auth.requests.post")
    def test_verify_token_invalid(self, mock_post, app):
        """Test verifying invalid token"""
        with app.app_context():
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"valid": False, "error": "Token expired"}
            mock_post.return_value = mock_response

            payload, error = verify_token_with_auth_service("invalid_token")
            assert payload is None
            assert "Token expired" in error

    @patch("app.utils.auth.requests.post")
    def test_verify_token_service_error(self, mock_post, app):
        """Test token verification when auth service returns error"""
        with app.app_context():
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.headers.get.return_value = "application/json"
            mock_response.json.return_value = {"error": "Internal server error"}
            mock_post.return_value = mock_response

            payload, error = verify_token_with_auth_service("some_token")
            assert payload is None
            assert error is not None

    @patch("app.utils.auth.requests.post")
    def test_verify_token_timeout(self, mock_post, app):
        """Test token verification when auth service times out"""
        with app.app_context():
            mock_post.side_effect = Exception("Timeout")

            payload, error = verify_token_with_auth_service("some_token")
            assert payload is None
            assert "error" in error.lower()

    @patch("app.utils.auth.verify_token_with_auth_service")
    def test_token_required_decorator_valid(self, mock_verify, app):
        """Test token_required decorator with valid token"""
        with app.test_request_context(headers={"Authorization": "Bearer valid_token"}):
            mock_verify.return_value = ({"user_id": 1, "role": "public"}, None)

            @token_required
            def test_func(current_user_id=None, current_user_role=None):
                return f"User {current_user_id} with role {current_user_role}"

            result = test_func()
            assert "User 1" in result
            assert "role public" in result

    def test_token_required_decorator_missing_token(self, app):
        """Test token_required decorator without token"""
        with app.test_request_context():

            @token_required
            def test_func(current_user_id=None, current_user_role=None):
                return "Success"

            result = test_func()
            assert result[1] == 401

    @patch("app.utils.auth.verify_token_with_auth_service")
    def test_admin_required_decorator_valid(self, mock_verify, app):
        """Test admin_required decorator with admin role"""
        with app.test_request_context(headers={"Authorization": "Bearer admin_token"}):
            mock_verify.return_value = ({"user_id": 1, "role": "admin"}, None)

            @admin_required
            def test_func(current_user_id=None, current_user_role=None):
                return f"Admin {current_user_id}"

            result = test_func()
            assert "Admin 1" in result

    @patch("app.utils.auth.verify_token_with_auth_service")
    def test_admin_required_decorator_not_admin(self, mock_verify, app):
        """Test admin_required decorator with non-admin role"""
        with app.test_request_context(headers={"Authorization": "Bearer user_token"}):
            mock_verify.return_value = ({"user_id": 1, "role": "public"}, None)

            @admin_required
            def test_func(current_user_id=None, current_user_role=None):
                return "Success"

            result = test_func()
            assert result[1] == 403
