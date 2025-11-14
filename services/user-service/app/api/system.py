"""
System endpoints for health checks and service info
"""
import logging

from flask import Blueprint, current_app, jsonify
from app import db

system_bp = Blueprint("system", __name__)
logger = logging.getLogger(__name__)


@system_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        db.session.execute(db.text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error("Database health check failed", extra={"error": str(e)})
        db_status = f"unhealthy: {str(e)}"

    status_code = 200 if db_status == "healthy" else 503
    return (
        jsonify(
            {
                "status": "healthy" if db_status == "healthy" else "unhealthy",
                "service": "user-service",
                "version": "1.0.0",
                "database": db_status,
            }
        ),
        status_code,
    )


@system_bp.route("/", methods=["GET"])
def index():
    """Root endpoint with service information"""
    logger.debug("Service info requested")
    return (
        jsonify(
            {
                "service": "user-service",
                "version": "1.0.0",
                "description": "User profile management service",
                "endpoints": {"health": "/health", "current_user": "/users/me", "users": "/users"},
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
            "title": current_app.config.get("SERVICE_NAME", "User Service"),
            "version": current_app.config.get("SERVICE_VERSION", "1.0.0"),
            "description": "User profile management microservice with JWT-based authentication and role-based access control.",
            "contact": {"name": "API Support", "email": "support@example.com"},
        },
        "servers": [{"url": "http://localhost:5001", "description": "Development server"}],
        "tags": [
            {"name": "Users", "description": "User profile management endpoints"},
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
            "/users/me": {
                "get": {
                    "tags": ["Users"],
                    "summary": "Get current user profile",
                    "description": "Get the authenticated user's profile",
                    "security": [{"BearerAuth": []}],
                    "responses": {
                        "200": {
                            "description": "User profile retrieved successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "user": {
                                                "type": "object",
                                                "description": "User profile object",
                                            }
                                        },
                                    }
                                }
                            },
                        },
                        "401": {"description": "Unauthorized - Invalid or missing token"},
                        "404": {"description": "User not found"},
                    },
                },
                "put": {
                    "tags": ["Users"],
                    "summary": "Update current user profile",
                    "description": "Update the authenticated user's profile (first_name, last_name, country_code only)",
                    "security": [{"BearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "first_name": {"type": "string"},
                                        "last_name": {"type": "string"},
                                        "country_code": {
                                            "type": "string",
                                            "pattern": "^[A-Z]{3}$",
                                            "description": "ISO 3166-1 alpha-3 country code",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Profile updated successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "message": {"type": "string"},
                                            "user": {"type": "object"},
                                        },
                                    }
                                }
                            },
                        },
                        "400": {"description": "Invalid input or no valid fields to update"},
                        "401": {"description": "Unauthorized"},
                    },
                },
                "patch": {
                    "tags": ["Users"],
                    "summary": "Partially update current user profile",
                    "description": "Partially update the authenticated user's profile",
                    "security": [{"BearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "first_name": {"type": "string"},
                                        "last_name": {"type": "string"},
                                        "country_code": {
                                            "type": "string",
                                            "pattern": "^[A-Z]{3}$",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Profile updated successfully"},
                        "400": {"description": "Invalid input"},
                        "401": {"description": "Unauthorized"},
                    },
                },
            },
            "/users/{user_id}": {
                "get": {
                    "tags": ["Users"],
                    "summary": "Get user by ID",
                    "description": "Get a user profile by ID (own profile or admin only)",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "User ID",
                        }
                    ],
                    "responses": {
                        "200": {"description": "User profile retrieved successfully"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Access denied"},
                        "404": {"description": "User not found"},
                    },
                },
                "put": {
                    "tags": ["Users"],
                    "summary": "Update user by ID",
                    "description": "Update a user profile by ID (admin only)",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "first_name": {"type": "string"},
                                        "last_name": {"type": "string"},
                                        "email": {"type": "string", "format": "email"},
                                        "country_code": {"type": "string", "pattern": "^[A-Z]{3}$"},
                                        "role": {
                                            "type": "string",
                                            "enum": ["admin", "public", "government", "staff"],
                                        },
                                        "status": {
                                            "type": "string",
                                            "enum": ["active", "inactive", "suspended", "pending"],
                                        },
                                        "notes": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "User updated successfully"},
                        "400": {"description": "Invalid input"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Admin access required"},
                    },
                },
                "patch": {
                    "tags": ["Users"],
                    "summary": "Partially update user by ID",
                    "description": "Partially update a user profile by ID (admin only)",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "first_name": {"type": "string"},
                                        "last_name": {"type": "string"},
                                        "email": {"type": "string", "format": "email"},
                                        "country_code": {"type": "string"},
                                        "role": {"type": "string"},
                                        "status": {"type": "string"},
                                        "notes": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "User updated successfully"},
                        "400": {"description": "Invalid input"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Admin access required"},
                    },
                },
                "delete": {
                    "tags": ["Users"],
                    "summary": "Delete user by ID",
                    "description": "Delete a user by ID (admin only, cannot delete self)",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "User deleted successfully"},
                        "400": {"description": "Cannot delete your own account"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Admin access required"},
                    },
                },
            },
            "/users": {
                "get": {
                    "tags": ["Users"],
                    "summary": "List all users",
                    "description": "List all users with pagination and filtering (admin only)",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 1, "minimum": 1},
                            "description": "Page number",
                        },
                        {
                            "name": "per_page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                            "description": "Items per page",
                        },
                        {
                            "name": "role",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["admin", "public", "government", "staff"]},
                            "description": "Filter by role",
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["active", "inactive", "suspended", "pending"]},
                            "description": "Filter by status",
                        },
                        {
                            "name": "country_code",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Filter by country code",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Users list retrieved successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "users": {"type": "array", "items": {"type": "object"}},
                                            "total": {"type": "integer"},
                                            "page": {"type": "integer"},
                                            "per_page": {"type": "integer"},
                                            "pages": {"type": "integer"},
                                        },
                                    }
                                }
                            },
                        },
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Admin access required"},
                    },
                },
            },
            "/users/search": {
                "get": {
                    "tags": ["Users"],
                    "summary": "Search users",
                    "description": "Search users by email, first name, or last name (admin only)",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Search query",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                            "description": "Maximum number of results",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Search completed successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "users": {"type": "array", "items": {"type": "object"}},
                                            "count": {"type": "integer"},
                                        },
                                    }
                                }
                            },
                        },
                        "400": {"description": "Search query is required"},
                        "401": {"description": "Unauthorized"},
                        "403": {"description": "Admin access required"},
                    },
                },
            },
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            }
        },
    }

    return jsonify(spec), 200
