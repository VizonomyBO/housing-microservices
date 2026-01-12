"""
Authentication API endpoints - FastAPI version
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import Config
from app.dependencies import AuthenticatedUser, DatabaseSession
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utils.email import EmailClient, SesConfig
from app.utils.request_guard import GuardRule, SimpleRequestGuard
from app.utils.security import generate_reset_token, verify_password

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

ERROR_NO_DATA = "No data provided"
ERROR_UNEXPECTED = "An unexpected error occurred"
ERROR_UNKNOWN = "Unknown error"
ERROR_AUTH_FAILED = "Authentication failed"
ERROR_TOO_MANY_REQUESTS = "Request limit exceeded. Please try again later."

_request_guard = SimpleRequestGuard(
    {
        "register": GuardRule(5, 60),
        "login": GuardRule(10, 60),
        "refresh": GuardRule(20, 60),
        "logout": GuardRule(10, 60),
        "forgot_password": GuardRule(3, 3600),
        "reset_password": GuardRule(5, 3600),
        "change_password": GuardRule(5, 3600),
    }
)


# Pydantic models for request/response
class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "username": "johndoe",
                "password": "SecurePass123!",
                "first_name": "John",
                "last_name": "Doe",
                "country_code": "USA",
                "role": "public",
            }
        }
    )

    email: EmailStr = Field(..., description="User email address", examples=["user@example.com"])
    username: str = Field(
        ...,
        min_length=3,
        max_length=80,
        description="Username (3-80 characters)",
        examples=["johndoe"],
    )
    password: str = Field(
        ...,
        min_length=8,
        description="User password (minimum 8 characters)",
        examples=["SecurePass123!"],
    )
    first_name: str | None = Field(None, description="User's first name", examples=["John"])
    last_name: str | None = Field(None, description="User's last name", examples=["Doe"])
    country_code: str = Field(
        default="USA",
        pattern="^[A-Z]{3}$",
        description="ISO country code (3 uppercase letters)",
        examples=["USA"],
    )
    role: str = Field(
        default="public",
        pattern="^(admin|public|government|staff)$",
        description="User role",
        examples=["public"],
    )


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"login": "user@example.com", "password": "SecurePass123!"}}
    )

    login: str = Field(..., description="Email address or username", examples=["user@example.com"])
    password: str = Field(..., description="User password", examples=["SecurePass123!"])


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = Field(
        default=None,
        description="Refresh token (optional if using cookies)",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(
        default=None,
        description="Refresh token to revoke (optional if using cookies)",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(
        ..., description="Email address for password reset", examples=["user@example.com"]
    )


class ResetPasswordRequest(BaseModel):
    token: str = Field(
        ..., description="Password reset token received via email", examples=["abc123def456"]
    )
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password (minimum 8 characters)",
        examples=["NewSecurePass123!"],
    )


class VerifyTokenRequest(BaseModel):
    token: str | None = Field(
        default=None,
        description="Access token to verify (alternative to access_token field)",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )
    access_token: str | None = Field(
        default=None,
        description="Access token to verify (alternative to token field)",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password", examples=["OldPassword123!"])
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password (minimum 8 characters)",
        examples=["NewSecurePass123!"],
    )


def _get_config(request: Request):
    """Get config from app state"""
    return request.app.state.config


def _should_apply_guard(config: Config) -> bool:
    """Determine if in-process request guards should be enforced."""
    return getattr(config, "ENABLE_SIMPLE_GUARDS", True) and not getattr(config, "TESTING", False)


def _guard_request(scope: str, request: Request) -> None:
    """Apply a lightweight guard in lieu of external rate limiters."""
    config = _get_config(request)
    if not _should_apply_guard(config):
        return

    identity = request.client.host if request.client else "unknown"
    if not _request_guard.allow(scope, identity):
        logger.warning(
            "Request blocked by guard",
            extra={"scope": scope, "identity": identity},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=ERROR_TOO_MANY_REQUESTS,
        )


def _set_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    access_token_expires: datetime,
    refresh_token_expires: datetime,
    cookie_secure: bool,
):
    """Set authentication cookies on response"""
    response.set_cookie(
        key="access_token",
        value=access_token,
        expires=access_token_expires,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        expires=refresh_token_expires,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookies(response: Response, cookie_secure: bool):
    """Clear authentication cookies"""
    # cookie_secure parameter kept for API consistency, not used for deletion
    response.delete_cookie(key="access_token", path="/", samesite="lax")
    response.delete_cookie(key="refresh_token", path="/", samesite="lax")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: Request, session: DatabaseSession, payload: RegisterRequest
) -> JSONResponse:
    """
    Register a new user.
    """
    try:
        _guard_request("register", request)
        logger.info(
            "Attempting to create user",
            extra={"email": payload.email, "username": payload.username},
        )
        user, error = UserService.create_user(
            session,
            email=payload.email,
            username=payload.username,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            country_code=payload.country_code,
            role=payload.role,
        )

        if error:
            status_code = (
                status.HTTP_409_CONFLICT
                if "already" in error.lower()
                else status.HTTP_400_BAD_REQUEST
            )
            logger.warning(
                "User creation failed",
                extra={
                    "email": payload.email,
                    "username": payload.username,
                    "error": error,
                    "status_code": status_code,
                },
            )
            raise HTTPException(status_code=status_code, detail=error)

        if user is None:
            logger.error(
                "User creation returned None without error",
                extra={"email": payload.email, "username": payload.username},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user"
            )

        logger.info(
            "User registered successfully",
            extra={
                "user_id": user.id,
                "email": payload.email,
                "username": payload.username,
                "country_code": payload.country_code,
                "role": payload.role,
            },
        )
        return JSONResponse(
            {"message": "User registered successfully", "user": user.to_dict()},
            status_code=status.HTTP_201_CREATED,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during user registration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ERROR_UNEXPECTED
        ) from None


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    session: DatabaseSession,
    payload: LoginRequest,
) -> JSONResponse:
    """
    Authenticate user and return access and refresh tokens.
    """
    try:
        _guard_request("login", request)
        if not payload.login or not payload.password:
            logger.warning("Login attempt with missing credentials")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Login and password are required"
            )

        # Authenticate user
        logger.info("Authentication attempt", extra={"login_identifier": payload.login})
        try:
            user, error = AuthService.authenticate_user(session, payload.login, payload.password)
        except Exception:
            logger.exception(
                "Database error during authentication",
                extra={"login_identifier": payload.login},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_AUTH_FAILED
            ) from None

        if error or user is None:
            logger.warning(
                "Authentication failed",
                extra={
                    "login_identifier": payload.login,
                    "error": error if error else ERROR_UNKNOWN,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error if error else ERROR_AUTH_FAILED,
            )

        config = _get_config(request)
        access_token = AuthService.generate_access_token(user, config)

        user_agent = request.headers.get("User-Agent")
        ip_address = request.client.host if request.client else None

        refresh_token = AuthService.generate_refresh_token(
            session, user, user_agent, ip_address, config
        )

        UserService.update_last_login(session, user)

        access_token_expires = datetime.now(UTC) + config.JWT_ACCESS_TOKEN_EXPIRES
        refresh_token_expires = datetime.now(UTC) + config.JWT_REFRESH_TOKEN_EXPIRES

        cookie_secure = config.COOKIE_SECURE

        _set_cookies(
            response,
            access_token,
            refresh_token,
            access_token_expires,
            refresh_token_expires,
            cookie_secure,
        )

        logger.info("Login successful", extra={"user_id": user.id, "username": user.username})
        return JSONResponse(
            {
                "message": "Login successful",
                "user": user.to_dict(),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": int(config.JWT_ACCESS_TOKEN_EXPIRES.total_seconds()),
            }
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during login")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ERROR_UNEXPECTED
        ) from None


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest,
    session: DatabaseSession,
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
) -> JSONResponse:
    """
    Refresh access token using a valid refresh token.
    Supports both cookie-based and JSON body-based refresh tokens.
    """
    try:
        _guard_request("refresh", request)
        refresh_token = refresh_token_cookie or payload.refresh_token

        if not refresh_token:
            logger.warning("Token refresh attempt with missing refresh token")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token is required"
            )

        logger.info("Attempting to refresh token")
        config = _get_config(request)
        new_access_token, new_refresh_token, error = AuthService.refresh_access_token(
            session, refresh_token, config
        )

        if error or new_access_token is None or new_refresh_token is None:
            logger.warning(
                "Token refresh failed", extra={"error": error if error else ERROR_UNKNOWN}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error if error else "Failed to refresh token",
            )

        config = _get_config(request)
        access_token_expires = datetime.now(UTC) + config.JWT_ACCESS_TOKEN_EXPIRES
        refresh_token_expires = datetime.now(UTC) + config.JWT_REFRESH_TOKEN_EXPIRES

        cookie_secure = config.COOKIE_SECURE

        _set_cookies(
            response,
            new_access_token,
            new_refresh_token,
            access_token_expires,
            refresh_token_expires,
            cookie_secure,
        )

        logger.info("Token refreshed successfully")
        return JSONResponse(
            {
                "message": "Token refreshed successfully",
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_in": int(config.JWT_ACCESS_TOKEN_EXPIRES.total_seconds()),
            }
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during token refresh")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ERROR_UNEXPECTED
        ) from None


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest,
    session: DatabaseSession,
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
) -> JSONResponse:
    """
    Logout user by revoking refresh token.
    Supports both cookie-based and JSON body-based refresh tokens.
    """
    try:
        _guard_request("logout", request)
        refresh_token = refresh_token_cookie or payload.refresh_token

        if not refresh_token:
            logger.warning("Logout attempt with missing refresh token")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token is required"
            )

        logger.info("Revoking refresh token")
        AuthService.revoke_refresh_token(session, refresh_token)

        config = _get_config(request)
        _clear_cookies(response, config.COOKIE_SECURE)

        logger.info("Logout successful")
        return JSONResponse({"message": "Logout successful"})

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during logout")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ERROR_UNEXPECTED
        ) from None


@router.post("/forgot-password")
async def forgot_password(
    request: Request, payload: ForgotPasswordRequest, session: DatabaseSession
) -> JSONResponse:
    """
    Request password reset token.
    """
    try:
        _guard_request("forgot_password", request)
        logger.info("Password reset request", extra={"email": payload.email})
        user = UserService.get_user_by_email(session, payload.email)

        if user:
            reset_token = generate_reset_token()
            # Store as naive UTC datetime for DB compatibility
            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

            if UserService.set_reset_token(session, user, reset_token, expires_at):
                logger.info(
                    "Password reset token generated",
                    extra={"user_id": user.id, "email": payload.email},
                )
                config = _get_config(request)
                reset_url = f"{config.PASSWORD_RESET_URL}?token={reset_token}"
                if not config.SES_SOURCE_EMAIL:
                    logger.warning(
                        "SES source email not configured; skip sending reset email",
                        extra={"email": payload.email},
                    )
                else:
                    try:
                        ses_config = SesConfig(
                            region=config.SES_REGION,
                            source_email=config.SES_SOURCE_EMAIL,
                            configuration_set=config.SES_CONFIGURATION_SET or None,
                        )
                        EmailClient(ses_config).send_password_reset_email(
                            to_email=payload.email,
                            reset_url=reset_url,
                            token=reset_token,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to send password reset email via SES",
                            extra={"email": payload.email},
                        )
            else:
                logger.error(
                    "Failed to set reset token", extra={"user_id": user.id, "email": payload.email}
                )

        return JSONResponse({"message": "If the email exists, a password reset link has been sent"})

    except Exception:
        logger.exception("Unexpected error during password reset request")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ERROR_UNEXPECTED
        ) from None


@router.post("/reset-password")
async def reset_password(
    request: Request, payload: ResetPasswordRequest, session: DatabaseSession
) -> JSONResponse:
    """
    Reset password using a valid reset token.
    """
    try:
        _guard_request("reset_password", request)
        from app.models.user import User

        logger.info("Attempting password reset with token")
        user = session.query(User).filter_by(reset_token=payload.token).first()

        if not user:
            logger.warning("Password reset attempt with invalid token")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token"
            )

        # Compare as naive UTC datetimes (DB stores naive, so strip tzinfo for comparison)
        now_utc = datetime.now(UTC).replace(tzinfo=None)
        if not user.reset_token_expires or now_utc > user.reset_token_expires:
            logger.warning("Password reset attempt with expired token", extra={"user_id": user.id})
            UserService.clear_reset_token(session, user)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token has expired"
            )

        success, error = UserService.update_password(session, user, payload.new_password)

        if not success:
            logger.warning("Password update failed", extra={"user_id": user.id, "error": error})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

        UserService.clear_reset_token(session, user)

        AuthService.revoke_all_user_tokens(session, user.id)

        logger.info("Password reset successful", extra={"user_id": user.id})
        return JSONResponse(
            {"message": "Password reset successful. Please login with your new password."}
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during password reset")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ERROR_UNEXPECTED
        ) from None


@router.get("/verify-token")
@router.post("/verify-token")
async def verify_token(
    request: Request,
) -> JSONResponse:
    """
    Verify if an access token is valid.

    Uses middleware-validated user context from request.state.user.
    Token can be provided via:
    - Authorization: Bearer <token> header (preferred)
    - access_token cookie
    - JSON body with 'token' or 'access_token' field (POST only)

    Returns user context if token is valid, or error if invalid/missing.
    """
    # Middleware already validated token and populated request.state.user if valid
    user_context = getattr(request.state, "user", None)

    if not user_context:
        logger.warning("Token verification failed: no valid token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )

    # Convert UserContext to dict format for response
    from app.utils.token_validator import create_validation_response

    payload_data = {
        "user_id": user_context.user_id,
        "username": user_context.username,
        "email": user_context.email,
        "role": user_context.roles[0] if user_context.roles else "public",
        "roles": user_context.roles,
        "country_code": user_context.country_code,
    }

    logger.info("Token verified successfully", extra={"user_id": user_context.user_id})
    return JSONResponse(create_validation_response(payload_data))


@router.post("/change-password")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    user: AuthenticatedUser,
    session: DatabaseSession,
) -> JSONResponse:
    """
    Change password for authenticated user.
    Requires current password and new password.
    """
    try:
        _guard_request("change_password", request)
        user_id = user.user_id

        # Get user directly from database
        from app.models.user import User

        db_user = session.query(User).filter_by(user_id=user_id).first()
        if not db_user:
            logger.warning("User not found for password change", extra={"user_id": user_id})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Verify current password
        # Extract password_hash value (SQLAlchemy Column[str] returns str at runtime)
        password_hash: str = db_user.password_hash  # type: ignore[assignment]
        if not verify_password(password_hash, payload.current_password):
            logger.warning(
                "Password change failed: incorrect current password", extra={"user_id": user_id}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect"
            )

        # Update password
        success, error = UserService.update_password(session, db_user, payload.new_password)
        if not success:
            logger.warning("Password update failed", extra={"user_id": user_id, "error": error})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

        # Revoke all tokens to force re-login
        AuthService.revoke_all_user_tokens(session, db_user.id)

        logger.info("Password changed successfully", extra={"user_id": user_id})
        return JSONResponse({"message": "Password changed successfully"})

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during password change")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ERROR_UNEXPECTED
        ) from None
