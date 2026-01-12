"""Assertion helpers for testing API responses."""

from typing import Any

from app.utils.enums import ErrorCode


def assert_error_response(
    response: Any,
    expected_status: int,
    expected_code: ErrorCode | None = None,
    expected_message: str | None = None,
) -> dict[str, Any]:
    """
    Assert that response is a valid error response.

    Args:
        response: Flask test response object
        expected_status: Expected HTTP status code
        expected_code: Expected error code
        expected_message: Expected error message (substring match)

    Returns:
        Response JSON data for further assertions
    """
    assert (
        response.status_code == expected_status
    ), f"Expected status {expected_status}, got {response.status_code}"

    data = response.get_json()
    assert data is not None, "Response should contain JSON data"
    assert "error" in data or "code" in data, "Response should contain error information"

    # Handle both direct error responses and wrapped error responses
    error_data = data.get("error", data)

    if expected_code:
        assert "code" in error_data, "Error response should contain 'code' field"
        assert (
            error_data["code"] == expected_code.value
        ), f"Expected error code {expected_code.value}, got {error_data.get('code')}"

    if expected_message:
        assert "message" in error_data, "Error response should contain 'message' field"
        message = error_data["message"].lower()
        expected = expected_message.lower()
        assert (
            expected in message
        ), f"Expected message to contain '{expected_message}', got '{error_data['message']}'"

    return data


def assert_success_response(
    response: Any,
    expected_status: int = 200,
    expected_message: str | None = None,
) -> dict[str, Any]:
    """
    Assert that response is a successful response.

    Args:
        response: Flask test response object
        expected_status: Expected HTTP status code
        expected_message: Expected success message (substring match)

    Returns:
        Response JSON data for further assertions
    """
    assert (
        response.status_code == expected_status
    ), f"Expected status {expected_status}, got {response.status_code}"

    data = response.get_json()
    assert data is not None, "Response should contain JSON data"

    if expected_message:
        assert "message" in data, "Success response should contain 'message' field"
        message = data["message"].lower()
        expected = expected_message.lower()
        assert (
            expected in message
        ), f"Expected message to contain '{expected_message}', got '{data['message']}'"

    return data


def assert_valid_token(token: str) -> None:
    """
    Assert that a token string is valid (non-empty and properly formatted).

    Args:
        token: JWT token string
    """
    assert token is not None, "Token should not be None"
    assert isinstance(token, str), "Token should be a string"
    assert len(token) > 0, "Token should not be empty"
    # JWT tokens have 3 parts separated by dots
    parts = token.split(".")
    assert len(parts) == 3, "Token should have 3 parts (header.payload.signature)"


def assert_user_data(
    data: dict[str, Any],
    expected_email: str | None = None,
    expected_status: str | None = None,
) -> None:
    """
    Assert that user data contains expected fields.

    Args:
        data: User data dictionary
        expected_email: Expected email address
        expected_status: Expected user status
    """
    required_fields = ["id", "email", "status", "role"]
    for field in required_fields:
        assert field in data, f"User data should contain '{field}' field"

    if expected_email:
        assert (
            data["email"] == expected_email
        ), f"Expected email {expected_email}, got {data['email']}"

    if expected_status:
        assert (
            data["status"] == expected_status
        ), f"Expected status {expected_status}, got {data['status']}"


def assert_has_keys(data: dict[str, Any], *keys: str) -> None:
    """
    Assert that data contains specified keys.

    Args:
        data: Dictionary to check
        keys: Keys that should be present
    """
    for key in keys:
        assert key in data, f"Data should contain '{key}' field"
