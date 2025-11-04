"""
User management API endpoints
"""

from flask import Blueprint, jsonify, request

from app import limiter
from app.services.user_service import UserService
from app.utils.auth_decorators import require_admin, require_auth
from app.utils.validators import sanitize_string, validate_email, validate_password

users_bp = Blueprint("users", __name__)


@users_bp.route("", methods=["GET"])
@require_auth
@require_admin
@limiter.limit("30 per minute")
def list_users(current_user, token_payload):
    """
    Get a paginated list of users.
    - Admins can view all users
    - Can filter by status (active, pending, inactive, suspended)
    - Can filter by role (admin, public, government, staff)
    - Supports pagination with page and per_page parameters
    """
    # Get query parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    status = request.args.get("status", type=str)
    role = request.args.get("role", type=str)

    # Validate page
    if page < 1:
        return jsonify({"error": "Page must be greater than 0"}), 400

    # Validate per_page
    if per_page < 1 or per_page > 100:
        return jsonify({"error": "per_page must be between 1 and 100"}), 400

    # Get users with pagination
    try:
        users, total = UserService.list_users(
            page=page,
            per_page=per_page,
            status=status,
            role=role,
        )

        # Calculate pagination metadata
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        return jsonify({
            "users": [user.to_dict() for user in users],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve users: {str(e)}"}), 500


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@require_auth
@require_admin
@limiter.limit("10 per hour")
def delete_user(user_id: int, current_user, token_payload):
    """
    Delete a user by ID.
    Requires admin role.
    """
    # Prevent self-deletion
    if user_id == current_user.user_id:
        return jsonify({"error": "Cannot delete your own account"}), 400

    # Get user to delete (allow inactive/pending users)
    user = UserService.get_user_by_id(user_id, active_only=False)
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        # Delete user (cascade will handle related records)
        from app import db

        db.session.delete(user)
        db.session.commit()

        return jsonify({"message": f"User {user_id} deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete user: {str(e)}"}), 500


@users_bp.route("/<int:user_id>/approve", methods=["PUT", "PATCH"])
@require_auth
@require_admin
@limiter.limit("20 per hour")
def approve_user(user_id: int, current_user, token_payload):
    """
    Approve a user by changing status from pending to active.
    Requires admin role.
    """
    user = UserService.get_user_by_id(user_id, active_only=False)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.status == "active":
        return jsonify({"error": "User is already active"}), 400

    try:
        user.status = "active"
        from app import db

        db.session.commit()

        return jsonify({"message": f"User {user_id} approved successfully", "user": user.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to approve user: {str(e)}"}), 500


@users_bp.route("/<int:user_id>", methods=["PUT", "PATCH"])
@require_auth
@limiter.limit("20 per hour")
def update_user(user_id: int, current_user, token_payload):
    """
    Update user details.
    - Admins can update any user account (user settings for admins)
    - Non-admin users can only update their own account
    - Users can update their own profile: first_name, last_name, password, country_code
    - Only admins can change the role field
    
    Note: 'organization' field is not in the current schema. If needed, add it to the User model.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Get user to update (allow inactive/pending users)
    user = UserService.get_user_by_id(user_id, active_only=False)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Check permissions: admins can update any account (user settings for admins)
    # Non-admin users can only update their own account
    is_admin = current_user.role == "admin"
    is_own_account = current_user.user_id == user_id

    if not is_admin and not is_own_account:
        return jsonify({"error": "You can only update your own account"}), 403

    # Check if trying to change role
    if "role" in data:
        if not is_admin:
            return jsonify({"error": "Only admins can change user roles"}), 403

    try:
        from app import db
        from app.utils.security import hash_password

        # Update first_name
        if "first_name" in data:
            first_name = data.get("first_name")
            if not first_name or len(first_name.strip()) == 0:
                return jsonify({"error": "First name cannot be empty"}), 400
            user.first_name = sanitize_string(first_name, 100)

        # Update last_name
        if "last_name" in data:
            last_name = data.get("last_name")
            if not last_name or len(last_name.strip()) == 0:
                return jsonify({"error": "Last name cannot be empty"}), 400
            user.last_name = sanitize_string(last_name, 100)

        # Update password
        if "password" in data:
            new_password = data.get("password")
            is_valid, error = validate_password(new_password)
            if not is_valid:
                return jsonify({"error": error}), 400
            user.password_hash = hash_password(new_password)

        # Update country_code
        if "country_code" in data:
            country_code = data.get("country_code")
            if not country_code or len(country_code) != 3:
                return jsonify({"error": "Country code must be 3 characters (ISO format)"}), 400
            user.country_code = country_code.upper()

        # Update role (only if admin)
        if "role" in data:
            if is_admin:
                role = data.get("role")
                valid_roles = ["admin", "public", "government", "staff"]
                if role not in valid_roles:
                    return (
                        jsonify({"error": f"Role must be one of: {', '.join(valid_roles)}"}),
                        400,
                    )
                user.role = role
            # Already checked above, but double-check
            else:
                return jsonify({"error": "Only admins can change user roles"}), 403

        # Note: organization field not in current schema
        # If you need it, add to User model: organization = db.Column(db.String(255))
        if "organization" in data:
            return jsonify({"error": "Organization field not available in current schema"}), 400

        db.session.commit()

        return jsonify({"message": f"User {user_id} updated successfully", "user": user.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update user: {str(e)}"}), 500

