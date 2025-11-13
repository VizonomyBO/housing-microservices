"""
System endpoints for health checks and API documentation
"""

from datetime import datetime, timezone

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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
                    "description": "Create a new user account with email, username, and password",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["email", "username", "password"],
                                    "properties": {
                                        "email": {"type": "string", "format": "email"},
                                        "username": {
                                            "type": "string",
                                            "minLength": 3,
                                            "maxLength": 80,
                                            "description": "Unique username",
                                        },
                                        "password": {"type": "string", "minLength": 8},
                                        "first_name": {
                                            "type": "string",
                                            "description": "Optional first name",
                                        },
                                        "last_name": {
                                            "type": "string",
                                            "description": "Optional last name",
                                        },
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
                                            "message": {
                                                "type": "string",
                                                "example": "User registered successfully",
                                            },
                                            "user": {
                                                "type": "object",
                                                "description": "User object with created user details",
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid input",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "error": {
                                                "type": "string",
                                                "example": "Missing required field(s): email, username",
                                            }
                                        },
                                    }
                                }
                            },
                        },
                        "409": {
                            "description": "User already exists",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "error": {
                                                "type": "string",
                                                "example": "Email already registered",
                                            }
                                        },
                                    }
                                }
                            },
                        },
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
                                            "description": "Email address or username",
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
                                            "message": {
                                                "type": "string",
                                                "example": "Login successful",
                                            },
                                            "access_token": {"type": "string"},
                                            "refresh_token": {"type": "string"},
                                            "token_type": {"type": "string", "example": "Bearer"},
                                            "expires_in": {"type": "integer"},
                                            "user": {"type": "object"},
                                        },
                                    }
                                }
                            },
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
                                                    "Account is inactive. Please contact support.",
                                                ],
                                                "example": "Invalid credentials",
                                            }
                                        },
                                    }
                                }
                            },
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
            "/auth/forgot-password": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "Forgot password",
                    "description": "Request a password reset token",
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
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            }
        },
    }

    return jsonify(spec), 200
