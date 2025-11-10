"""
System endpoints for health checks and API documentation
"""

from datetime import datetime

from flask import Blueprint, current_app, jsonify

from app import db

system_bp = Blueprint("system", __name__)


@system_bp.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint.
    ---
    tags:
      - System
    responses:
      200:
        description: Service is healthy
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: healthy
                timestamp:
                  type: string
                  format: date-time
                service:
                  type: string
                  example: Account Management Service
    """
    # Check database connection
    try:
        db.session.execute(db.text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return (
        jsonify(
            {
                "status": "healthy" if db_status == "connected" else "degraded",
                "timestamp": datetime.utcnow().isoformat(),
                "service": current_app.config["APP_NAME"],
                "version": current_app.config["APP_VERSION"],
                "database": db_status,
            }
        ),
        200,
    )


@system_bp.route("/status", methods=["GET"])
def status():
    """
    Service status endpoint with detailed information.
    ---
    tags:
      - System
    responses:
      200:
        description: Service status information
    """
    return (
        jsonify(
            {
                "service": current_app.config["APP_NAME"],
                "version": current_app.config["APP_VERSION"],
                "timestamp": datetime.utcnow().isoformat(),
                "endpoints": {
                    "health": "/health",
                    "status": "/status",
                    "openapi": "/openapi.json",
                    "auth": "/auth/*",
                },
            }
        ),
        200,
    )


@system_bp.route("/openapi.json", methods=["GET"])
def openapi_spec():
    """
    OpenAPI specification endpoint.
    """
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": current_app.config["APP_NAME"],
            "version": current_app.config["APP_VERSION"],
            "description": "Secure authentication and account management microservice with JWT-based authentication, password reset, and user management capabilities.",
            "contact": {"name": "API Support", "email": "support@example.com"},
        },
        "servers": [{"url": "http://localhost:5000", "description": "Development server"}],
        "tags": [
            {"name": "Authentication", "description": "User authentication and token management"},
            {"name": "System", "description": "System health and status endpoints"},
            {"name": "User Management", "description": "User management and administration endpoints"},
            {"name": "Document Management", "description": "Document management and retrieval endpoints"},
        ],
        "paths": {
            "/health": {
                "get": {
                    "tags": ["System"],
                    "summary": "Health check",
                    "description": "Check if the service is running and healthy",
                    "responses": {
                        "200": {
                            "description": "Service is healthy",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"},
                                            "timestamp": {"type": "string"},
                                            "service": {"type": "string"},
                                            "version": {"type": "string"},
                                            "database": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/auth/register": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "Register a new user",
                    "description": "Create a new user account with email, password, and personal information",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["email", "password", "first_name", "last_name"],
                                    "properties": {
                                        "email": {"type": "string", "format": "email"},
                                        "password": {"type": "string", "minLength": 8},
                                        "first_name": {"type": "string", "minLength": 1},
                                        "last_name": {"type": "string", "minLength": 1},
                                        "country_code": {
                                            "type": "string",
                                            "pattern": "^[A-Z]{3}$",
                                            "description": "ISO 3166-1 alpha-3 country code",
                                            "default": "USA",
                                        },
                                        "role": {
                                            "type": "string",
                                            "enum": ["admin", "public", "government", "staff"],
                                            "default": "public",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "User created successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "message": {"type": "string", "example": "User registered successfully"},
                                            "user": {
                                                "type": "object",
                                                "description": "Note: New users are created with status='pending' and must be activated before login"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "400": {"description": "Invalid input"},
                        "409": {"description": "User already exists"},
                    },
                }
            },
            "/auth/login": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "User login",
                    "description": "Authenticate user and receive access and refresh tokens",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["login", "password"],
                                    "properties": {
                                        "login": {
                                            "type": "string",
                                            "format": "email",
                                            "description": "Email address",
                                        },
                                        "password": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Login successful",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "message": {"type": "string", "example": "Login successful"},
                                            "access_token": {"type": "string"},
                                            "refresh_token": {"type": "string"},
                                            "token_type": {"type": "string", "example": "Bearer"},
                                            "expires_in": {"type": "integer"},
                                            "user": {"type": "object"}
                                        }
                                    }
                                }
                            }
                        },
                        "401": {
                            "description": "Authentication failed",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "error": {
                                                "type": "string",
                                                "enum": [
                                                    "Invalid credentials",
                                                    "Account is pending activation. Please verify your email or contact support.",
                                                    "Account has been suspended. Please contact support.",
                                                    "Account is inactive. Please contact support."
                                                ],
                                                "example": "Invalid credentials"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    },
                }
            },
            "/auth/refresh": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "Refresh access token",
                    "description": "Get a new access token using a valid refresh token",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["refresh_token"],
                                    "properties": {"refresh_token": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Token refreshed successfully"},
                        "401": {"description": "Invalid or expired token"},
                    },
                }
            },
            "/auth/logout": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "User logout",
                    "description": "Revoke refresh token",
                    "security": [{"BearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["refresh_token"],
                                    "properties": {"refresh_token": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Logout successful"}},
                }
            },
            "/auth/me": {
                "get": {
                    "tags": ["Authentication"],
                    "summary": "Get current user",
                    "description": "Get the current authenticated user's information. Requires Bearer token in Authorization header.",
                    "security": [{"BearerAuth": []}],
                    "responses": {
                        "200": {
                            "description": "Current user information",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "user_id": {"type": "integer", "format": "int64"},
                                            "first_name": {"type": "string"},
                                            "last_name": {"type": "string"},
                                            "email": {"type": "string", "format": "email"},
                                            "email_verified": {"type": "boolean"},
                                            "role": {"type": "string", "enum": ["admin", "public", "government", "staff"]},
                                            "status": {"type": "string", "enum": ["active", "pending", "inactive", "suspended"]},
                                            "country_code": {"type": "string", "pattern": "^[A-Z]{3}$"},
                                            "date_created": {"type": "string", "format": "date-time"},
                                            "date_modified": {"type": "string", "format": "date-time"},
                                            "created_by": {"type": ["integer", "null"], "format": "int64"},
                                        },
                                    },
                                }
                            },
                        },
                        "401": {"description": "Unauthorized - Invalid or missing token"},
                        "403": {"description": "Forbidden - User account is not active"},
                    },
                }
            },
            "/auth/forgot-password": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "Forgot password",
                    "description": "Request a password reset token. An email with the reset token will be sent via AWS SES to the provided email address if it exists in the system.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["email"],
                                    "properties": {"email": {"type": "string", "format": "email"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Reset email sent"}},
                }
            },
            "/auth/reset-password": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "Reset password",
                    "description": "Reset password using a valid reset token",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["token", "new_password"],
                                    "properties": {
                                        "token": {"type": "string"},
                                        "new_password": {"type": "string", "minLength": 8},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Password reset successful"},
                        "400": {"description": "Invalid or expired token"},
                    },
                }
            },
            "/users": {
                "get": {
                    "tags": ["User Management"],
                    "summary": "List users",
                    "description": "Get a paginated list of users. Admins can view all users. Can filter by status (active, pending, inactive, suspended) and role (admin, public, government, staff). Supports pagination with page and per_page parameters.",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "page",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1, "default": 1},
                            "description": "Page number (1-indexed)",
                        },
                        {
                            "name": "per_page",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                            "description": "Number of items per page (max 100)",
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["active", "pending", "inactive", "suspended"]},
                            "description": "Filter by user status",
                        },
                        {
                            "name": "role",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["admin", "public", "government", "staff"]},
                            "description": "Filter by user role",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "List of users with pagination metadata",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "users": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "user_id": {"type": "integer", "format": "int64"},
                                                        "first_name": {"type": "string"},
                                                        "last_name": {"type": "string"},
                                                        "email": {"type": "string", "format": "email"},
                                                        "email_verified": {"type": "boolean"},
                                                        "role": {"type": "string", "enum": ["admin", "public", "government", "staff"]},
                                                        "status": {"type": "string", "enum": ["active", "pending", "inactive", "suspended"]},
                                                        "country_code": {"type": "string", "pattern": "^[A-Z]{3}$"},
                                                        "date_created": {"type": "string", "format": "date-time"},
                                                        "date_modified": {"type": "string", "format": "date-time"},
                                                        "created_by": {"type": ["integer", "null"], "format": "int64"},
                                                    },
                                                },
                                            },
                                            "pagination": {
                                                "type": "object",
                                                "properties": {
                                                    "page": {"type": "integer"},
                                                    "per_page": {"type": "integer"},
                                                    "total": {"type": "integer"},
                                                    "total_pages": {"type": "integer"},
                                                    "has_next": {"type": "boolean"},
                                                    "has_prev": {"type": "boolean"},
                                                },
                                            },
                                        },
                                    },
                                }
                            },
                        },
                        "400": {"description": "Invalid pagination parameters"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Admin access required"},
                        "500": {"description": "Internal server error"},
                    },
                }
            },
            "/users/{user_id}": {
                "delete": {
                    "tags": ["User Management"],
                    "summary": "Delete user",
                    "description": "Delete a user by ID. Requires admin role.",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "User ID to delete",
                        }
                    ],
                    "responses": {
                        "200": {"description": "User deleted successfully"},
                        "400": {"description": "Cannot delete own account"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Admin access required"},
                        "404": {"description": "User not found"},
                    },
                },
                "put": {
                    "tags": ["User Management"],
                    "summary": "Update user",
                    "description": "Update user details. Admins can update any user account (user settings for admins). Non-admin users can only update their own account. Users can update their own profile (first_name, last_name, password, country_code). Only admins can change the role field.",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "User ID to update",
                        }
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "first_name": {"type": "string", "minLength": 1},
                                        "last_name": {"type": "string", "minLength": 1},
                                        "password": {"type": "string", "minLength": 8, "description": "New password"},
                                        "country_code": {
                                            "type": "string",
                                            "pattern": "^[A-Z]{3}$",
                                            "description": "ISO 3166-1 alpha-3 country code",
                                        },
                                        "role": {
                                            "type": "string",
                                            "enum": ["admin", "public", "government", "staff"],
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "User updated successfully"},
                        "400": {"description": "Invalid input"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Forbidden - cannot update other users or change role without admin access"},
                        "404": {"description": "User not found"},
                    },
                },
            },
            "/users/{user_id}/approve": {
                "put": {
                    "tags": ["User Management"],
                    "summary": "Approve user",
                    "description": "Approve a user by changing status from pending to active. Requires admin role.",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "User ID to approve",
                        }
                    ],
                    "responses": {
                        "200": {"description": "User approved successfully"},
                        "400": {"description": "User already active"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Admin access required"},
                        "404": {"description": "User not found"},
                    },
                }
            },
            "/documents": {
                "get": {
                    "tags": ["Document Management"],
                    "summary": "List documents",
                    "description": "Get a paginated list of documents. Requires authentication. Can filter by status, access_level, country_code, user_uploaded, and validated. Supports pagination with page and per_page parameters.",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "page",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1, "default": 1},
                            "description": "Page number (1-indexed)",
                        },
                        {
                            "name": "per_page",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                            "description": "Number of items per page (max 100)",
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["pending", "processing", "validated", "rejected", "archived"]},
                            "description": "Filter by document status",
                        },
                        {
                            "name": "access_level",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["public", "restricted", "confidential", "internal"]},
                            "description": "Filter by access level",
                        },
                        {
                            "name": "country_code",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "pattern": "^[A-Z]{3}$"},
                            "description": "Filter by country code (ISO 3-letter code)",
                        },
                        {
                            "name": "user_uploaded",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "format": "int64"},
                            "description": "Filter by uploader user_id",
                        },
                        {
                            "name": "validated",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "boolean"},
                            "description": "Filter by validation status",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "List of documents with pagination metadata",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "documents": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "document_id": {"type": "integer", "format": "int64"},
                                                        "filename": {"type": "string"},
                                                        "file_path": {"type": "string"},
                                                        "file_size": {"type": "integer", "format": "int64"},
                                                        "file_type": {"type": "string"},
                                                        "mime_type": {"type": "string"},
                                                        "file_hash": {"type": "string"},
                                                        "country_code": {"type": "string"},
                                                        "date_uploaded": {"type": "string", "format": "date-time"},
                                                        "date_modified": {"type": "string", "format": "date-time"},
                                                        "user_uploaded": {"type": "integer", "format": "int64"},
                                                        "source": {"type": ["string", "null"]},
                                                        "validated": {"type": "boolean"},
                                                        "validated_by": {"type": ["integer", "null"], "format": "int64"},
                                                        "validated_at": {"type": ["string", "null"], "format": "date-time"},
                                                        "document_status": {"type": "string"},
                                                        "access_level": {"type": "string"},
                                                    },
                                                },
                                            },
                                            "pagination": {
                                                "type": "object",
                                                "properties": {
                                                    "page": {"type": "integer"},
                                                    "per_page": {"type": "integer"},
                                                    "total": {"type": "integer"},
                                                    "total_pages": {"type": "integer"},
                                                    "has_next": {"type": "boolean"},
                                                    "has_prev": {"type": "boolean"},
                                                },
                                            },
                                        },
                                    },
                                }
                            },
                        },
                        "400": {"description": "Invalid pagination parameters"},
                        "401": {"description": "Unauthorized"},
                        "500": {"description": "Internal server error"},
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            },
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "format": "int64"},
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                        "email_verified": {"type": "boolean"},
                        "role": {"type": "string", "enum": ["admin", "public", "government", "staff"]},
                        "status": {"type": "string", "enum": ["active", "pending", "inactive", "suspended"]},
                        "country_code": {"type": "string", "pattern": "^[A-Z]{3}$"},
                        "date_created": {"type": "string", "format": "date-time"},
                        "date_modified": {"type": "string", "format": "date-time"},
                        "created_by": {"type": "integer", "format": "int64", "nullable": True},
                    },
                }
            }
        },
    }

    return jsonify(spec), 200
