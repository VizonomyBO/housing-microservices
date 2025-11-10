"""
Document management API endpoints
"""

from flask import Blueprint, jsonify, request

from app import limiter
from app.services.document_service import DocumentService
from app.utils.auth_decorators import require_auth

documents_bp = Blueprint("documents", __name__)


@documents_bp.route("", methods=["GET"])
@require_auth
@limiter.limit("30 per minute")
def list_documents(current_user, token_payload):
    """
    Get a paginated list of documents.
    - Requires authentication
    - Can filter by status, access_level, country_code, user_uploaded, validated
    - Supports pagination with page and per_page parameters
    """
    # Get query parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    document_status = request.args.get("status", type=str)
    access_level = request.args.get("access_level", type=str)
    country_code = request.args.get("country_code", type=str)
    user_uploaded = request.args.get("user_uploaded", type=int)
    validated = request.args.get("validated", type=str)

    # Validate page
    if page < 1:
        return jsonify({"error": "Page must be greater than 0"}), 400

    # Validate per_page
    if per_page < 1 or per_page > 100:
        return jsonify({"error": "per_page must be between 1 and 100"}), 400

    # Convert validated string to boolean if provided
    validated_bool = None
    if validated is not None:
        validated_bool = validated.lower() in ('true', '1', 'yes')

    # Get documents with pagination
    try:
        documents, total = DocumentService.list_documents(
            page=page,
            per_page=per_page,
            document_status=document_status,
            access_level=access_level,
            country_code=country_code,
            user_uploaded=user_uploaded,
            validated=validated_bool,
        )

        # Calculate pagination metadata
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        return jsonify({
            "documents": [doc.to_dict() for doc in documents],
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
        return jsonify({"error": f"Failed to retrieve documents: {str(e)}"}), 500

