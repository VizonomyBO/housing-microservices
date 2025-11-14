"""
User management API endpoints
"""
import logging

from flask import Blueprint, jsonify, request

from app.services.user_service import UserService
from app.utils.auth import token_required, admin_required

users_bp = Blueprint("users", __name__)
logger = logging.getLogger(__name__)


@users_bp.route("/me", methods=["GET"])
@token_required
def get_current_user(**kwargs):
    """Get current user profile"""
    current_user_id = kwargs.get("current_user_id")

    logger.info("Get current user request", extra={"user_id": current_user_id})
    user = UserService.get_user_by_id(current_user_id)
    if not user:
        logger.warning("User not found", extra={"user_id": current_user_id})
        return jsonify({"error": "User not found"}), 404

    logger.info("User profile retrieved", extra={"user_id": current_user_id})
    return jsonify({"user": user.to_dict()}), 200


@users_bp.route("/me", methods=["PUT", "PATCH"])
@token_required
def update_current_user(**kwargs):
    """Update current user profile"""
    current_user_id = kwargs.get("current_user_id")
    data = request.get_json()

    if not data:
        logger.warning("Update profile attempt with no data", extra={"user_id": current_user_id})
        return jsonify({"error": "No data provided"}), 400

    allowed_fields = {"first_name", "last_name", "country_code"}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        logger.warning(
            "No valid fields to update", extra={"user_id": current_user_id, "data": data}
        )
        return jsonify({"error": "No valid fields to update"}), 400

    logger.info(
        "Updating user profile",
        extra={"user_id": current_user_id, "fields": list(update_data.keys())},
    )
    user, error = UserService.update_user(current_user_id, update_data, current_user_id)

    if error:
        logger.warning("Profile update failed", extra={"user_id": current_user_id, "error": error})
        return jsonify({"error": error}), 400

    logger.info("Profile updated successfully", extra={"user_id": current_user_id})
    return jsonify({"message": "Profile updated successfully", "user": user.to_dict()}), 200


@users_bp.route("/<int:user_id>", methods=["GET"])
@token_required
def get_user(user_id, **kwargs):
    """Get user by ID"""
    current_user_id = kwargs.get("current_user_id")
    current_user_role = kwargs.get("current_user_role")

    if current_user_role != "admin" and current_user_id != user_id:
        logger.warning(
            "Access denied to user profile",
            extra={"current_user_id": current_user_id, "requested_user_id": user_id},
        )
        return jsonify({"error": "Access denied"}), 403

    logger.info(
        "Get user request",
        extra={
            "current_user_id": current_user_id,
            "requested_user_id": user_id,
            "role": current_user_role,
        },
    )
    user = UserService.get_user_by_id(user_id)
    if not user:
        logger.warning("User not found", extra={"user_id": user_id})
        return jsonify({"error": "User not found"}), 404

    include_sensitive = current_user_role == "admin"
    logger.info("User profile retrieved", extra={"user_id": user_id, "by_user_id": current_user_id})
    return jsonify({"user": user.to_dict(include_sensitive=include_sensitive)}), 200


@users_bp.route("", methods=["GET"])
@admin_required
def list_users(**kwargs):
    """List all users with pagination and filtering"""
    current_user_id = kwargs.get("current_user_id")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    role = request.args.get("role")
    status = request.args.get("status")
    country_code = request.args.get("country_code")

    if page < 1:
        logger.warning("Invalid page parameter", extra={"page": page, "user_id": current_user_id})
        return jsonify({"error": "Page must be greater than 0"}), 400

    if per_page < 1 or per_page > 100:
        logger.warning(
            "Invalid per_page parameter", extra={"per_page": per_page, "user_id": current_user_id}
        )
        return jsonify({"error": "Per page must be between 1 and 100"}), 400

    logger.info(
        "List users request",
        extra={
            "user_id": current_user_id,
            "page": page,
            "per_page": per_page,
            "role": role,
            "status": status,
        },
    )
    result = UserService.get_all_users(
        page=page, per_page=per_page, role=role, status=status, country_code=country_code
    )

    logger.info(
        "Users list retrieved",
        extra={"user_id": current_user_id, "total": result["total"], "page": page},
    )
    return jsonify(result), 200


@users_bp.route("/<int:user_id>", methods=["PUT", "PATCH"])
@admin_required
def update_user(user_id, **kwargs):
    """Update user by ID"""
    current_user_id = kwargs.get("current_user_id")
    data = request.get_json()

    if not data:
        logger.warning(
            "Update user attempt with no data",
            extra={"admin_id": current_user_id, "target_user_id": user_id},
        )
        return jsonify({"error": "No data provided"}), 400

    allowed_fields = {"first_name", "last_name", "email", "country_code", "role", "status", "notes"}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        logger.warning(
            "No valid fields to update",
            extra={"admin_id": current_user_id, "target_user_id": user_id, "data": data},
        )
        return jsonify({"error": "No valid fields to update"}), 400

    logger.info(
        "Admin updating user",
        extra={
            "admin_id": current_user_id,
            "target_user_id": user_id,
            "fields": list(update_data.keys()),
        },
    )
    user, error = UserService.update_user(user_id, update_data, current_user_id)

    if error:
        logger.warning(
            "User update failed",
            extra={"admin_id": current_user_id, "target_user_id": user_id, "error": error},
        )
        return jsonify({"error": error}), 400

    logger.info(
        "User updated successfully", extra={"admin_id": current_user_id, "target_user_id": user_id}
    )
    return (
        jsonify(
            {"message": "User updated successfully", "user": user.to_dict(include_sensitive=True)}
        ),
        200,
    )


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id, **kwargs):
    """Delete user by ID"""
    current_user_id = kwargs.get("current_user_id")

    if current_user_id == user_id:
        logger.warning("Admin attempted to delete own account", extra={"admin_id": current_user_id})
        return jsonify({"error": "Cannot delete your own account"}), 400

    logger.info(
        "Admin deleting user", extra={"admin_id": current_user_id, "target_user_id": user_id}
    )
    success, error = UserService.delete_user(user_id)

    if not success:
        logger.warning(
            "User deletion failed",
            extra={"admin_id": current_user_id, "target_user_id": user_id, "error": error},
        )
        return jsonify({"error": error}), 400

    logger.info(
        "User deleted successfully", extra={"admin_id": current_user_id, "deleted_user_id": user_id}
    )
    return jsonify({"message": "User deleted successfully"}), 200


@users_bp.route("/search", methods=["GET"])
@admin_required
def search_users(**kwargs):
    """Search users by email, first name, or last name"""
    current_user_id = kwargs.get("current_user_id")
    query = request.args.get("q")

    if not query:
        logger.warning("Search attempt without query", extra={"admin_id": current_user_id})
        return jsonify({"error": "Search query is required"}), 400

    limit = request.args.get("limit", 10, type=int)
    if limit < 1 or limit > 50:
        logger.warning("Invalid search limit", extra={"admin_id": current_user_id, "limit": limit})
        return jsonify({"error": "Limit must be between 1 and 50"}), 400

    logger.info(
        "User search request", extra={"admin_id": current_user_id, "query": query, "limit": limit}
    )
    users = UserService.search_users(query, limit)

    logger.info(
        "Search completed", extra={"admin_id": current_user_id, "results_count": len(users)}
    )
    return jsonify({"users": [user.to_dict() for user in users], "count": len(users)}), 200
