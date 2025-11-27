"""
FastAPI authentication and context middleware

Intercepts /v1/* requests, validates JWT tokens, extracts user context,
and injects it into request.state. Also handles correlation IDs and error responses.
"""

import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

DEFAULT_AUTH_SERVICE_URL = "http://localhost:5001"
DEFAULT_HTTP_TIMEOUT = 5.0
API_PATH_PREFIX = "/v1/"
BEARER_PREFIX = "bearer"
MIN_TOKEN_LENGTH = 10
TRACEPARENT_SAMPLED_FLAG = "01"
TRACEPARENT_VERSION = "00"
HEADER_AUTHORIZATION = "Authorization"
HEADER_VIZ_REQUEST_ID = "Viz-Request-Id"
HEADER_TRACEPARENT = "Traceparent"
HEADER_CONTENT_TYPE = "Content-Type"
CONTENT_TYPE_JSON = "application/json"

# Public paths that don't require authentication
PUBLIC_PATHS = {
    "/v1/auth/login",
    "/v1/auth/register",
    "/v1/auth/verify-token",  # This endpoint validates tokens, so it must be public
    "/v1/auth/forgot-password",
    "/v1/auth/reset-password",
    "/v1/auth/refresh",  # Refresh uses refresh token, not access token
    "/v1/auth/logout",  # Logout uses refresh token, not access token
    "/v1/health",
    "/v1/",
}

# Error codes (per API contract §1.1)
ERROR_CODE_UNAUTHORIZED = "UNAUTHORIZED"
ERROR_CODE_FORBIDDEN = "FORBIDDEN"

ERROR_MSG_MISSING_TOKEN = "Missing authentication token"
ERROR_MSG_INVALID_TOKEN = "Invalid token"
ERROR_MSG_TOKEN_VERIFICATION_FAILED = "Token verification failed"
ERROR_MSG_AUTH_SERVICE_TIMEOUT = "Auth service timeout"
ERROR_MSG_AUTH_SERVICE_UNAVAILABLE = "Auth service unavailable"
ERROR_MSG_TOKEN_VERIFICATION_ERROR = "Token verification error"
ERROR_MSG_INVALID_RESPONSE = "Invalid response from auth service"
ERROR_MSG_INVALID_USER_DATA = "Invalid user data in response"


@dataclass
class UserContext:
    """User context extracted from JWT token"""

    user_id: int
    roles: list[str]
    country_code: str
    username: str | None = None
    email: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary"""
        return {
            "user_id": self.user_id,
            "roles": self.roles,
            "country_code": self.country_code,
            "username": self.username,
            "email": self.email,
        }


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for FastAPI

    Intercepts /v1/* requests, validates JWT tokens, extracts user context,
    and injects it into request.state. Also handles correlation IDs and error responses.
    """

    def __init__(
        self,
        app: ASGIApp,
        auth_service_url: str | None = None,
        mock_validation: bool = False,
        use_direct_validation: bool = True,
    ):
        """
        Initialize authentication middleware

        Args:
            app: FastAPI application
            auth_service_url: URL of the auth service for token validation (for remote validation)
            mock_validation: If True, use mock validation for local development
            use_direct_validation: If True, use direct function call instead of HTTP (faster)
        """
        super().__init__(app)
        self.app = app  # Store app reference to access config
        self.auth_service_url = auth_service_url or os.getenv(
            "AUTH_SERVICE_URL", DEFAULT_AUTH_SERVICE_URL
        )
        self.mock_validation = (
            mock_validation or os.getenv("MOCK_AUTH_VALIDATION", "false").lower() == "true"
        )
        self.use_direct_validation = (
            use_direct_validation
            and os.getenv("USE_DIRECT_TOKEN_VALIDATION", "true").lower() == "true"
        )

        # Try to import direct validator (will fail if not in same service)
        self._direct_validator = None
        if self.use_direct_validation:
            try:
                # Attempt to import from auth-service
                from app.utils.token_validator import verify_token_direct

                self._direct_validator = verify_token_direct
                logger.info("Using direct token validation (no HTTP overhead)")
            except ImportError:
                logger.info("Direct token validation not available, using HTTP")
                self.use_direct_validation = False

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Process request through authentication middleware

        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler

        Returns:
            Response with user context injected or error response
        """
        request_id = self._get_or_generate_request_id(request)
        traceparent = self._get_or_generate_traceparent(request)

        request.state.request_id = request_id
        request.state.traceparent = traceparent

        if not request.url.path.startswith(API_PATH_PREFIX):
            response = await call_next(request)
            return self._add_correlation_headers(response, request_id, traceparent)

        # Check if this is a public path
        is_public_path = request.url.path in PUBLIC_PATHS

        # Try to extract and validate token (even for public paths)
        # This allows user context to be populated if a valid token is provided
        token = self._extract_token(request)
        user_context = None
        validation_error = None

        if token:
            # Validate token if present (even for public paths)
            user_context, validation_error = await self._validate_token(token, request)
            if not validation_error and user_context:
                # Token is valid, populate user context
                request.state.user = user_context

        # For protected paths, require valid authentication
        if not is_public_path:
            if not token:
                logger.warning(
                    "Authentication failed: missing token",
                    extra={
                        "path": request.url.path,
                        "method": request.method,
                        "request_id": request_id,
                    },
                )
                return self._error_response(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    error_code=ERROR_CODE_UNAUTHORIZED,
                    message=ERROR_MSG_MISSING_TOKEN,
                    request_id=request_id,
                    traceparent=traceparent,
                )

            # Check if token validation failed
            if validation_error or user_context is None:
                error_code = ERROR_CODE_UNAUTHORIZED
                status_code = status.HTTP_401_UNAUTHORIZED

                # Check if it's a permission issue (403) vs authentication issue (401)
                if validation_error and (
                    "permission" in validation_error.lower()
                    or "forbidden" in validation_error.lower()
                ):
                    error_code = ERROR_CODE_FORBIDDEN
                    status_code = status.HTTP_403_FORBIDDEN

                logger.warning(
                    "Authentication failed: token validation error",
                    extra={
                        "path": request.url.path,
                        "method": request.method,
                        "error": validation_error or "Invalid token",
                        "error_code": error_code,
                        "request_id": request_id,
                    },
                )
                return self._error_response(
                    status_code=status_code,
                    error_code=error_code,
                    message=validation_error or "Invalid or expired token",
                    request_id=request_id,
                    traceparent=traceparent,
                )

        # For public paths, proceed even without token (user context populated if token was valid)
        # For protected paths, we've already validated above
        response = await call_next(request)

        # Automatically inject user context into JSON responses if available
        response = self._inject_user_context_to_response(response, user_context)

        return self._add_correlation_headers(response, request_id, traceparent)

    def _extract_token(self, request: Request) -> str | None:
        """
        Extract JWT token from Authorization header

        Args:
            request: FastAPI request object

        Returns:
            Token string if found, None otherwise
        """
        auth_header = request.headers.get(HEADER_AUTHORIZATION)
        if not auth_header:
            return None

        parts = auth_header.split(maxsplit=1)
        if len(parts) != 2 or parts[0].lower() != BEARER_PREFIX:
            return None

        return parts[1]

    async def _validate_token(
        self, token: str, request: Request | None = None
    ) -> tuple[UserContext | None, str | None]:
        """
        Validate JWT token and extract user context

        Args:
            token: JWT token string
            request: Optional request object to get config from app state

        Returns:
            Tuple of (UserContext, None) on success or (None, error_message) on failure
        """
        if self.mock_validation:
            return self._mock_validate_token(token)

        # Use direct validation if available (faster, no HTTP overhead)
        if self.use_direct_validation and self._direct_validator:
            return await self._validate_token_direct(token, request)

        # Fall back to HTTP validation for remote services
        return await self._validate_token_http(token)

    async def _validate_token_direct(
        self, token: str, request: Request | None = None
    ) -> tuple[UserContext | None, str | None]:
        """
        Validate token using direct function call (no HTTP overhead)

        Args:
            token: JWT token string
            request: Optional request object to get config from app state

        Returns:
            Tuple of (UserContext, None) on success or (None, error_message) on failure
        """
        try:
            # Call validator in executor to avoid blocking async loop
            import asyncio

            if not self._direct_validator:
                return None, ERROR_MSG_TOKEN_VERIFICATION_ERROR

            # Get config from request or app state
            config = None
            if request:
                config = getattr(request.app.state, "config", None)
            elif hasattr(self.app, "state"):
                config = getattr(self.app.state, "config", None)

            loop = asyncio.get_event_loop()
            validator_func = self._direct_validator
            # Pass config to validator if available
            if config:
                payload, error = await loop.run_in_executor(
                    None, lambda: validator_func(token, config)
                )
            else:
                payload, error = await loop.run_in_executor(None, validator_func, token)

            if error or not payload:
                return None, error or ERROR_MSG_INVALID_TOKEN

            # Enrich payload with user data from database
            # The JWT token doesn't include role and country_code, so we need to fetch them
            user_id = payload.get("user_id")
            if not isinstance(user_id, int):
                logger.error("Invalid user_id in token payload", extra={"user_id": user_id})
                return None, ERROR_MSG_INVALID_USER_DATA

            # Look up user in database to get role and country_code
            try:
                from app.database import get_session
                from app.models.user import User

                def enrich_payload_with_user_data():
                    """Enrich payload with user data from database"""
                    session = get_session()
                    try:
                        user = session.query(User).filter_by(user_id=user_id).first()
                        if user:
                            payload["role"] = user.role
                            payload["roles"] = [user.role] if user.role else []
                            payload["country_code"] = user.country_code
                            # Update username and email from database if not in token
                            if not payload.get("username") and user.email:
                                payload["username"] = user.email.split("@")[0]
                            if not payload.get("email") and user.email:
                                payload["email"] = user.email
                        else:
                            logger.warning(
                                "User not found in database for token",
                                extra={"user_id": user_id},
                            )
                            # Use defaults if user not found
                            payload.setdefault("role", "public")
                            payload.setdefault("roles", ["public"])
                            payload.setdefault("country_code", "USA")
                    finally:
                        session.close()

                # Run database query in executor to avoid blocking
                await loop.run_in_executor(None, enrich_payload_with_user_data)
            except Exception as db_error:
                logger.warning(
                    "Failed to enrich payload with user data from database",
                    extra={"user_id": user_id, "error": str(db_error)},
                )
                # Use defaults if database lookup fails
                payload.setdefault("role", "public")
                payload.setdefault("roles", ["public"])
                payload.setdefault("country_code", "USA")

            # Extract roles - support both 'roles' (list) and 'role' (string)
            roles = payload.get("roles")
            if not roles:
                role = payload.get("role")
                roles = [role] if role else []

            # Convert roles to list of strings
            role_list: list[str] = []
            if isinstance(roles, list):
                role_list = [str(r) for r in roles if r]
            elif roles:
                role_list = [str(roles)]

            country_code = payload.get("country_code", "USA")
            username = payload.get("username")
            email = payload.get("email")

            return (
                UserContext(
                    user_id=user_id,
                    roles=role_list,
                    country_code=str(country_code) if country_code else "USA",
                    username=str(username) if username else None,
                    email=str(email) if email else None,
                ),
                None,
            )
        except Exception as e:
            logger.exception("Error in direct token validation", extra={"error": str(e)})
            return None, ERROR_MSG_TOKEN_VERIFICATION_ERROR

    async def _validate_token_http(self, token: str) -> tuple[UserContext | None, str | None]:
        """
        Validate token via HTTP call to auth service

        Args:
            token: JWT token string

        Returns:
            Tuple of (UserContext, None) on success or (None, error_message) on failure
        """
        try:
            timeout = httpx.Timeout(DEFAULT_HTTP_TIMEOUT, connect=2.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.auth_service_url}/v1/auth/verify-token",
                    json={"token": token},
                    headers={HEADER_CONTENT_TYPE: CONTENT_TYPE_JSON},
                )

                if response.status_code == status.HTTP_200_OK:
                    return self._process_successful_response(response)

                if response.status_code == status.HTTP_401_UNAUTHORIZED:
                    content_type = response.headers.get(HEADER_CONTENT_TYPE, "")
                    error_data = response.json() if CONTENT_TYPE_JSON in content_type else {}
                    return None, error_data.get("error", ERROR_MSG_TOKEN_VERIFICATION_FAILED)

                logger.warning(
                    ERROR_MSG_TOKEN_VERIFICATION_FAILED,
                    extra={
                        "status_code": response.status_code,
                        "response_preview": response.text[:200] if response.text else None,
                    },
                )
                return None, ERROR_MSG_TOKEN_VERIFICATION_FAILED

        except httpx.TimeoutException:
            logger.error(ERROR_MSG_AUTH_SERVICE_TIMEOUT)
            return None, ERROR_MSG_AUTH_SERVICE_TIMEOUT
        except httpx.RequestError as e:
            logger.error(ERROR_MSG_AUTH_SERVICE_UNAVAILABLE, extra={"error": str(e)})
            return None, ERROR_MSG_AUTH_SERVICE_UNAVAILABLE
        except Exception as e:
            logger.exception(ERROR_MSG_TOKEN_VERIFICATION_ERROR, extra={"error": str(e)})
            return None, ERROR_MSG_TOKEN_VERIFICATION_ERROR

    def _process_successful_response(
        self, response: httpx.Response
    ) -> tuple[UserContext | None, str | None]:
        """
        Process successful response from auth service

        Args:
            response: HTTP response from auth service

        Returns:
            Tuple of (UserContext, None) on success or (None, error_message) on failure
        """
        data = response.json()
        if not isinstance(data, dict):
            logger.error(
                "Invalid response format from auth service", extra={"data_type": type(data)}
            )
            return None, ERROR_MSG_INVALID_RESPONSE

        if data.get("valid"):
            user_id = data.get("user_id")
            if not isinstance(user_id, int):
                logger.error("Invalid user_id in response", extra={"user_id": user_id})
                return None, ERROR_MSG_INVALID_USER_DATA

            # Extract roles - support both 'roles' (list) and 'role' (string) for backward compatibility
            roles = data.get("roles")
            if not roles:
                role = data.get("role")
                roles = [role] if role else []

            return (
                UserContext(
                    user_id=user_id,
                    roles=roles if isinstance(roles, list) else [roles],
                    country_code=data.get("country_code", "USA"),
                    username=data.get("username"),
                    email=data.get("email"),
                ),
                None,
            )
        return None, data.get("error", ERROR_MSG_INVALID_TOKEN)

    def _mock_validate_token(self, token: str) -> tuple[UserContext | None, str | None]:
        """
        Mock token validation for local development

        Args:
            token: JWT token string

        Returns:
            Tuple of (UserContext, None) on success or (None, error_message) on failure
        """
        if not token or len(token) < MIN_TOKEN_LENGTH:
            return None, ERROR_MSG_INVALID_TOKEN

        logger.debug("Using mock token validation", extra={"token_length": len(token)})
        return (
            UserContext(
                user_id=1,
                roles=["public"],
                country_code="USA",
                username="mock_user",
                email="mock@example.com",
            ),
            None,
        )

    def _get_or_generate_request_id(self, request: Request) -> str:
        """
        Get request ID from header or generate new one

        Args:
            request: FastAPI request object

        Returns:
            Request ID string (UUID)
        """
        existing_id = request.headers.get(HEADER_VIZ_REQUEST_ID)
        if existing_id:
            return existing_id

        return str(uuid.uuid4())

    def _get_or_generate_traceparent(self, request: Request) -> str:
        """
        Get or generate W3C Traceparent header

        Args:
            request: FastAPI request object

        Returns:
            Traceparent string (W3C format: 00-<trace-id>-<parent-id>-<trace-flags>)
        """
        existing_traceparent = request.headers.get(HEADER_TRACEPARENT)
        if existing_traceparent:
            return existing_traceparent

        trace_id = uuid.uuid4().hex[:32]
        parent_id = uuid.uuid4().hex[:16]
        return f"{TRACEPARENT_VERSION}-{trace_id}-{parent_id}-{TRACEPARENT_SAMPLED_FLAG}"

    def _inject_user_context_to_response(
        self, response: Response, user_context: UserContext | None
    ) -> Response:
        """
        Automatically inject user context into JSON responses

        Args:
            response: FastAPI response object
            user_context: User context to inject (if available)

        Returns:
            Response with user context added to body (if JSON)
        """
        if not user_context:
            return response

        # Only modify JSON responses
        content_type = response.headers.get(HEADER_CONTENT_TYPE, "")
        if CONTENT_TYPE_JSON not in content_type:
            return response

        # Handle JSONResponse by accessing its content attribute
        if isinstance(response, JSONResponse):
            try:
                import json

                # JSONResponse stores content in response.body, but we need to access it properly
                # Try to get the original content from the response
                # JSONResponse has a 'body' property that's computed, but we can access the raw content
                if hasattr(response, "body") and response.body:
                    body_str = (
                        response.body.decode("utf-8")
                        if isinstance(response.body, bytes)
                        else str(response.body)
                    )
                    body_data = json.loads(body_str) if body_str else {}

                    # Add user context to the data
                    if isinstance(body_data, dict):
                        body_data["user"] = user_context.to_dict()

                        # Create new JSONResponse with updated content
                        return JSONResponse(
                            content=body_data,
                            status_code=response.status_code,
                            headers=dict(response.headers),
                        )
            except (
                json.JSONDecodeError,
                UnicodeDecodeError,
                AttributeError,
                KeyError,
                TypeError,
            ) as e:
                # If we can't parse or modify, log and return original response
                logger.debug(f"Could not inject user context into response: {e}")

        return response

    def _add_correlation_headers(
        self, response: Response, request_id: str, traceparent: str
    ) -> Response:
        """
        Add correlation headers to response

        Args:
            response: FastAPI response object
            request_id: Request ID to add
            traceparent: Traceparent to add

        Returns:
            Response with headers added
        """
        response.headers[HEADER_VIZ_REQUEST_ID] = request_id
        response.headers[HEADER_TRACEPARENT] = traceparent
        return response

    def _error_response(
        self,
        status_code: int,
        error_code: str,
        message: str,
        request_id: str,
        traceparent: str | None = None,
        details: dict | None = None,
        retry_after_sec: int | None = None,
    ) -> JSONResponse:
        """
        Create standardized error response in Error Envelope format

        Args:
            status_code: HTTP status code
            error_code: Error code enum (VALIDATION_ERROR, RATE_LIMITED, etc.)
            message: Error message
            request_id: Request ID for correlation
            traceparent: Optional traceparent (generated if not provided)
            details: Optional error details
            retry_after_sec: Optional retry after seconds (for rate limiting)

        Returns:
            JSONResponse with error envelope format
        """
        error_payload: dict[str, Any] = {
            "code": error_code,
            "message": message,
            "request_id": request_id,
        }

        if details:
            error_payload["details"] = details

        if retry_after_sec is not None:
            error_payload["retry_after_sec"] = retry_after_sec

        response = JSONResponse(
            status_code=status_code,
            content={"error": error_payload},
        )

        if not traceparent:
            traceparent = self._generate_traceparent_from_request_id(request_id)
        response.headers[HEADER_VIZ_REQUEST_ID] = request_id
        response.headers[HEADER_TRACEPARENT] = traceparent

        return response

    def _generate_traceparent_from_request_id(self, request_id: str) -> str:
        """
        Generate traceparent from request ID (for error responses)

        Args:
            request_id: Request ID

        Returns:
            Traceparent string
        """
        trace_id = uuid.uuid5(uuid.NAMESPACE_DNS, request_id).hex[:32]
        parent_id = uuid.uuid4().hex[:16]
        return f"{TRACEPARENT_VERSION}-{trace_id}-{parent_id}-{TRACEPARENT_SAMPLED_FLAG}"
