"""Pydantic schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _validate_password_strength(value: str) -> str:
    """Validate password meets minimum strength requirements."""
    if not value:
        raise ValueError("Password must not be empty")
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not any(char.isdigit() for char in value):
        raise ValueError("Password must contain at least one digit")
    if not any(char.isupper() for char in value):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(char.islower() for char in value):
        raise ValueError("Password must contain at least one lowercase letter")
    return value


# --- Authentication Schemas ---


class LoginRequest(BaseModel):
    """Schema for user login requests."""

    model_config = ConfigDict(extra="forbid")

    login: str = Field(..., min_length=1, description="Email or username")
    password: str = Field(..., min_length=1, description="User password")


class RegisterRequest(BaseModel):
    """Schema for user registration requests."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="User email address")
    username: str | None = Field(None, min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=8, description="User password")
    first_name: str | None = Field(None, max_length=100, description="First name")
    last_name: str | None = Field(None, max_length=100, description="Last name")
    country_code: str = Field(default="USA", max_length=3, description="Country code")
    role: str = Field(default="public", description="User role")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normalize email to lowercase."""
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Validate password strength."""
        return _validate_password_strength(value)


class RefreshTokenRequest(BaseModel):
    """Schema for token refresh requests."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(..., min_length=1, description="Refresh token")


class ForgotPasswordRequest(BaseModel):
    """Schema for forgot password requests."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="User email address")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normalize email to lowercase."""
        return str(value).strip().lower()


class ResetPasswordRequest(BaseModel):
    """Schema for password reset requests."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=1, description="Reset token")
    new_password: str = Field(..., min_length=8, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Validate password strength."""
        return _validate_password_strength(value)


# --- Response Schemas ---


class TokenResponse(BaseModel):
    """Schema for authentication token responses."""

    model_config = ConfigDict(extra="allow")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Schema for user data responses."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    user_id: str = Field(..., alias="id")
    email: EmailStr
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    status: str
    role: str
    country_code: str
    email_verified: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LoginResponse(BaseModel):
    """Schema for login responses."""

    model_config = ConfigDict(extra="allow")

    message: str
    user: UserResponse
    access_token: str
    refresh_token: str
    expires_in: int


class RegisterResponse(BaseModel):
    """Schema for registration responses."""

    model_config = ConfigDict(extra="allow")

    message: str
    user: UserResponse


# --- Validation Helper ---


def validate_request(schema_class: type[BaseModel], data: dict) -> BaseModel:
    """
    Validate request data against a Pydantic schema.

    Args:
        schema_class: Pydantic model class to validate against
        data: Request data dictionary

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If validation fails
    """
    try:
        return schema_class.model_validate(data)
    except Exception as e:
        raise ValueError(f"Validation error: {e!s}") from e
