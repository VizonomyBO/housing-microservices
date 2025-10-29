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
                                        },
                                        "password": {"type": "string", "minLength": 8},
                                        "first_name": {"type": "string"},
                                        "last_name": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {"description": "User created successfully"},
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
                                            "description": "Email or username",
                                        },
                                        "password": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Login successful"},
                        "401": {"description": "Invalid credentials"},
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
