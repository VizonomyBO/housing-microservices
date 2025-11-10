"""
Document management service layer
"""

from app import db
from app.models.document import Document


class DocumentService:
    """Service for document management operations"""

    @staticmethod
    def list_documents(
        page: int = 1,
        per_page: int = 10,
        document_status: str | None = None,
        access_level: str | None = None,
        country_code: str | None = None,
        user_uploaded: int | None = None,
        validated: bool | None = None,
    ) -> tuple[list[Document], int]:
        """
        List documents with pagination and optional filtering.

        Args:
            page: Page number (1-indexed)
            per_page: Number of items per page (max 100)
            document_status: Filter by status ('pending', 'processing', 'validated', 'rejected', 'archived')
            access_level: Filter by access level ('public', 'restricted', 'confidential', 'internal')
            country_code: Filter by country code (ISO 3-letter code)
            user_uploaded: Filter by uploader user_id
            validated: Filter by validation status (True/False)

        Returns:
            Tuple of (list of Document objects, total count)
        """
        # Validate and clamp per_page
        per_page = max(1, min(per_page, 100))
        page = max(1, page)

        # Build query
        query = Document.query

        # Apply document_status filter
        if document_status:
            valid_statuses = ['pending', 'processing', 'validated', 'rejected', 'archived']
            if document_status in valid_statuses:
                query = query.filter_by(document_status=document_status)

        # Apply access_level filter
        if access_level:
            valid_levels = ['public', 'restricted', 'confidential', 'internal']
            if access_level in valid_levels:
                query = query.filter_by(access_level=access_level)

        # Apply country_code filter
        if country_code:
            query = query.filter_by(country_code=country_code.upper())

        # Apply user_uploaded filter
        if user_uploaded:
            query = query.filter_by(user_uploaded=user_uploaded)

        # Apply validated filter
        if validated is not None:
            query = query.filter_by(validated=validated)

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * per_page
        documents = query.order_by(Document.date_uploaded.desc()).offset(offset).limit(per_page).all()

        return documents, total

    @staticmethod
    def get_document_by_id(document_id: int) -> Document | None:
        """
        Get a document by ID.

        Args:
            document_id: Document ID

        Returns:
            Document object or None if not found
        """
        return Document.query.get(document_id)

