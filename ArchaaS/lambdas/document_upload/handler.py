"""
Document Upload Lambda Handler - Simplified Flow

POST /v1/documents/upload
- User provides document metadata (name, type, size)
- Returns presigned S3 URL for direct upload
- NO HASH REQUIRED - hash is calculated after upload by preflight Lambda

Flow:
1. User calls this endpoint with metadata
2. User uploads file directly to S3 using presigned URL
3. S3 triggers preflight Lambda which calculates hash & checks duplicates
4. Preflight Lambda starts Step Function if new document
"""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from functools import wraps
from typing import Any

import aioboto3
from core.exceptions import (
    DatabaseError,
)
from core.exceptions import (
    ValidationError as AppValidationError,
)
from core.logging import get_logger
from db.repository import DocumentRepository
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = get_logger(__name__)

# Configuration from environment variables
S3_BUCKET = os.environ.get("RAW_DOCUMENTS_BUCKET", "vizonomy-raw-documents")
S3_KEY_PREFIX = os.environ.get("S3_KEY_PREFIX", "raw")
PRESIGNED_URL_EXPIRY = int(os.environ.get("PRESIGNED_URL_EXPIRY_SEC", "900"))
MAX_FILE_SIZE_BYTES = int(
    os.environ.get("MAX_FILE_SIZE_BYTES", str(100 * 1024 * 1024))
)  # 100MB

# Allowed source types and their MIME mappings
ALLOWED_SOURCE_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "txt": "text/plain",
    "md": "text/markdown",
    "html": "text/html",
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
}


class DocumentUploadRequest(BaseModel):
    """
    Request model for document upload endpoint.

    Note: content_hash is NOT required - it will be calculated
    after upload by the preflight Lambda.
    """

    document_name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(...)
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    language: str = Field(default="en", min_length=2, max_length=5)
    tags: list[str] = Field(default_factory=list)
    file_size_bytes: int = Field(...)
    access_scope: str = Field(default="user_private")
    callback_url: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v.lower() not in ALLOWED_SOURCE_TYPES:
            raise ValueError(
                f"Invalid source_type '{v}'. Allowed: {list(ALLOWED_SOURCE_TYPES.keys())}"
            )
        return v.lower()

    @field_validator("file_size_bytes")
    @classmethod
    def validate_file_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("file_size_bytes must be positive")
        if v > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"file_size_bytes exceeds limit of {MAX_FILE_SIZE_BYTES} bytes (100MB)"
            )
        return v

    @field_validator("access_scope")
    @classmethod
    def validate_access_scope(cls, v: str) -> str:
        valid_scopes = ["user_private", "org_shared", "base"]
        if v not in valid_scopes:
            raise ValueError(f"Invalid access_scope '{v}'. Allowed: {valid_scopes}")
        return v


class UploadInfo(BaseModel):
    """Presigned URL info for S3 upload."""

    url: str
    fields: dict[str, str]
    expires_in_sec: int


class DocumentUploadResponse(BaseModel):
    """Response model for document upload endpoint."""

    document_id: str
    status: str  # registered initially until preflight picks up the file
    upload: UploadInfo
    message: str
    request_id: str | None = None


# Helper functions
def async_handler(f):
    """Decorator to run async handlers in Lambda."""

    @wraps(f)
    def wrapper(event, context):
        return asyncio.get_event_loop().run_until_complete(f(event, context))

    return wrapper


def create_response(status_code: int, body: dict, request_id: str = None) -> dict:
    """Create API Gateway response."""
    if request_id:
        body["request_id"] = request_id

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Request-Id",
        },
        "body": json.dumps(body, default=str),
    }


def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict = None,
    request_id: str = None,
) -> dict:
    """Create error response."""
    body = {
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
        }
    }
    return create_response(status_code, body, request_id)


async def generate_presigned_url(
    s3_key: str,
    content_type: str,
    file_size: int,
) -> UploadInfo:
    """Generate S3 presigned POST URL for direct upload."""
    session = aioboto3.Session()

    async with session.client("s3") as s3:
        # Use presigned POST for browser-compatible uploads
        presigned = await s3.generate_presigned_post(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Fields={
                "Content-Type": content_type,
            },
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, file_size + 1024],  # Allow small overhead
            ],
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )

        return UploadInfo(
            url=presigned["url"],
            fields=presigned["fields"],
            expires_in_sec=PRESIGNED_URL_EXPIRY,
        )


def int_to_uuid(user_id: int) -> str:
    """
    Convert integer user_id to a deterministic UUID format.
    Uses UUID v5 with a namespace to ensure consistency.
    """
    # Use a fixed namespace UUID for user ID conversion
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
    return str(uuid.uuid5(namespace, f"user:{user_id}"))


def extract_user_from_event(event: dict) -> tuple[str, list[str]]:
    """
    Extract user_id and roles from the Lambda event.
    Tries API Gateway authorizer first, then falls back to JWT decode.
    Returns user_id as UUID string for database compatibility.
    """
    import base64

    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})

    # Try JWT claims from authorizer first
    claims = authorizer.get("claims", authorizer.get("lambda", {}))
    user_id = claims.get("sub") or claims.get("user_id")

    # If no authorizer claims, try to decode JWT from Authorization header
    if not user_id:
        headers = event.get("headers", {})
        auth_header = headers.get("authorization") or headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                # Decode JWT payload (middle part)
                parts = token.split(".")
                if len(parts) == 3:
                    # Add padding if needed
                    payload = parts[1]
                    payload += "=" * (4 - len(payload) % 4)
                    decoded = base64.urlsafe_b64decode(payload)
                    jwt_claims = json.loads(decoded)
                    user_id = jwt_claims.get("user_id") or jwt_claims.get("sub")
                    claims = jwt_claims
            except Exception as e:
                logger.warning(f"Failed to decode JWT: {e}")

    roles = claims.get("roles", [])
    if isinstance(roles, str):
        roles = roles.split(",")

    if not user_id:
        raise AppValidationError("Missing user_id in authorization context")

    # Prefer UUID inputs; fall back to deterministic int→UUID mapping for legacy tokens
    try:
        user_uuid = str(uuid.UUID(str(user_id)))
    except (ValueError, TypeError):
        try:
            user_uuid = int_to_uuid(int(user_id))
        except (ValueError, TypeError) as exc:
            raise AppValidationError("user_id must be a UUID string") from exc

    return user_uuid, roles


def validate_base_scope_access(access_scope: str, roles: list[str]) -> None:
    """Validate that only admin/service tokens can create base documents."""
    if access_scope == "base":
        allowed_roles = {"admin", "service"}
        if not any(role in allowed_roles for role in roles):
            raise AppValidationError(
                "Only admin/service roles can create base documents"
            )


@async_handler
async def handler(event: dict, context: Any) -> dict:
    """
    Main Lambda handler for document upload.

    This is a simplified flow:
    1. Validate request
    2. Create document record with UPLOADING status
    3. Return presigned URL for S3 upload

    After user uploads to S3, the preflight Lambda will:
    - Calculate the content hash
    - Check for duplicates
    - Start the Step Function if new document
    """
    request_id = event.get("requestContext", {}).get("requestId", str(uuid.uuid4()))

    logger.info(
        "Processing document upload request",
        extra={"request_id": request_id},
    )

    # Parse and validate request body
    try:
        body = json.loads(event.get("body", "{}"))
        request_data = DocumentUploadRequest(**body)
    except json.JSONDecodeError:
        return create_error_response(
            status_code=400,
            error_code="INVALID_JSON",
            message="Request body must be valid JSON",
            request_id=request_id,
        )
    except ValidationError as e:
        return create_error_response(
            status_code=400,
            error_code="VALIDATION_ERROR",
            message="Invalid request data",
            details={"errors": e.errors()},
            request_id=request_id,
        )

    # Extract user from token
    try:
        user_id, roles = extract_user_from_event(event)
    except AppValidationError as e:
        return create_error_response(
            status_code=401,
            error_code="UNAUTHORIZED",
            message=str(e),
            request_id=request_id,
        )

    # Validate access scope permissions
    try:
        validate_base_scope_access(request_data.access_scope, roles)
    except AppValidationError as e:
        return create_error_response(
            status_code=403,
            error_code="FORBIDDEN",
            message=str(e),
            request_id=request_id,
        )

    # Generate IDs
    document_id = str(uuid.uuid4())

    # Determine S3 key and content type
    file_extension = request_data.source_type
    content_type = ALLOWED_SOURCE_TYPES[request_data.source_type]
    s3_key = f"{S3_KEY_PREFIX}/{document_id}/source.{file_extension}"

    # Create document record with UPLOADING status
    repository = DocumentRepository()
    pending_hash = f"pending::{document_id}"

    metadata_payload = {
        **request_data.metadata,
        "callback_url": request_data.callback_url,
    }

    document_data = {
        "id": document_id,
        "owner_user_id": user_id if request_data.access_scope != "base" else None,
        "access_scope": request_data.access_scope,
        "canonical_name": request_data.document_name,
        "country_code": request_data.country_code,
        "language": request_data.language,
        "tags": request_data.tags,
        "status": "registered",
        # shared_data_layer migrations enforce NOT NULL, so stash a deterministic
        # placeholder until preflight updates the real SHA-256.
        "content_hash": pending_hash,
        "source_uri": f"s3://{S3_BUCKET}/{s3_key}",
        "byte_size": request_data.file_size_bytes,
        "metadata": metadata_payload,
        "created_at": datetime.now(UTC),
    }

    try:
        await repository.create_document(document_data)
    except DatabaseError as e:
        logger.error(
            "Failed to create document record",
            extra={"request_id": request_id, "error": str(e)},
        )
        return create_error_response(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="Failed to create document record",
            request_id=request_id,
        )

    # Generate presigned URL for upload
    try:
        upload_info = await generate_presigned_url(
            s3_key=s3_key,
            content_type=content_type,
            file_size=request_data.file_size_bytes,
        )
    except Exception as e:
        logger.error(
            "Failed to generate presigned URL",
            extra={"request_id": request_id, "error": str(e)},
        )
        return create_error_response(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="Failed to generate upload URL",
            request_id=request_id,
        )

    logger.info(
        "Document upload initiated",
        extra={
            "request_id": request_id,
            "document_id": document_id,
            "s3_key": s3_key,
        },
    )

    response = DocumentUploadResponse(
        document_id=document_id,
        status="registered",
        upload=upload_info,
        message="Upload your file to the presigned URL. After upload, the system will automatically validate and process your document.",
        request_id=request_id,
    )

    return create_response(
        status_code=201,
        body=response.model_dump(),
        request_id=request_id,
    )
