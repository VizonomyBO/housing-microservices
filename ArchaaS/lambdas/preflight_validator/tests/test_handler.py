"""
Unit tests for preflight validator Lambda handler.
"""

from unittest.mock import AsyncMock, patch

import pytest
from core.exceptions import (
    DuplicateDocumentError,
    ValidationPermanentError,
)
from handler import (
    MIME_TYPE_MAPPINGS,
    extract_source_type_from_key,
    validate_content_type,
    validate_magic_bytes,
)


class TestExtractSourceType:
    """Tests for source type extraction from S3 key."""

    def test_extract_pdf(self):
        assert extract_source_type_from_key("raw/ing-123/source.pdf") == "pdf"

    def test_extract_docx(self):
        assert extract_source_type_from_key("raw/ing-123/document.docx") == "docx"

    def test_extract_html(self):
        assert extract_source_type_from_key("raw/ing-123/page.html") == "html"

    def test_extract_csv(self):
        assert extract_source_type_from_key("raw/ing-123/data.csv") == "csv"

    def test_unsupported_extension(self):
        with pytest.raises(ValidationPermanentError) as exc_info:
            extract_source_type_from_key("raw/ing-123/file.txt")
        assert "Unsupported file extension" in str(exc_info.value)

    def test_uppercase_extension(self):
        assert extract_source_type_from_key("raw/ing-123/SOURCE.PDF") == "pdf"


class TestValidateMagicBytes:
    """Tests for magic bytes validation."""

    def test_pdf_valid(self):
        pdf_header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3"
        assert validate_magic_bytes(pdf_header, "pdf") is True

    def test_pdf_invalid(self):
        fake_pdf = b"This is not a PDF"
        assert validate_magic_bytes(fake_pdf, "pdf") is False

    def test_docx_valid(self):
        # DOCX starts with ZIP signature
        docx_header = b"PK\x03\x04"
        assert validate_magic_bytes(docx_header, "docx") is True

    def test_html_doctype(self):
        html_header = b"<!DOCTYPE html>"
        assert validate_magic_bytes(html_header, "html") is True

    def test_html_tag(self):
        html_header = b"<html>"
        assert validate_magic_bytes(html_header, "html") is True

    def test_csv_no_magic_bytes(self):
        # CSV doesn't have magic bytes, should always pass
        csv_data = b"col1,col2,col3\nval1,val2,val3"
        assert validate_magic_bytes(csv_data, "csv") is True


class TestValidateContentType:
    """Tests for Content-Type validation."""

    def test_pdf_valid(self):
        assert validate_content_type("application/pdf", "pdf") is True

    def test_pdf_with_charset(self):
        assert validate_content_type("application/pdf; charset=utf-8", "pdf") is True

    def test_docx_valid(self):
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert validate_content_type(content_type, "docx") is True

    def test_html_valid(self):
        assert validate_content_type("text/html", "html") is True

    def test_csv_text_csv(self):
        assert validate_content_type("text/csv", "csv") is True

    def test_csv_text_plain(self):
        assert validate_content_type("text/plain", "csv") is True

    def test_invalid_content_type(self):
        assert validate_content_type("image/png", "pdf") is False

    def test_unknown_source_type(self):
        assert validate_content_type("application/pdf", "xyz") is False


class TestMimeTypeMappings:
    """Tests for MIME type configuration."""

    def test_all_types_have_content_types(self):
        for source_type, config in MIME_TYPE_MAPPINGS.items():
            assert "content_types" in config
            assert len(config["content_types"]) > 0

    def test_supported_types(self):
        expected_types = {"pdf", "docx", "html", "csv"}
        assert set(MIME_TYPE_MAPPINGS.keys()) == expected_types


@pytest.mark.asyncio
class TestHandlerIntegration:
    """Integration tests for the handler function."""

    async def test_missing_required_fields(self):
        """Test handler rejects missing required fields."""
        from handler import handler

        event = {
            "ingestion_id": "ing-123",
            # Missing document_id and s3_key
        }

        with pytest.raises(ValidationPermanentError) as exc_info:
            await handler.__wrapped__(event, None)

        assert "Missing required fields" in str(exc_info.value)

    @patch("handler.DocumentRepository")
    @patch("handler.get_s3_object_metadata")
    async def test_document_not_found(self, mock_s3_meta, mock_repo_class):
        """Test handler fails when document not found."""
        from handler import handler

        mock_repo = AsyncMock()
        mock_repo.get_document_by_id.return_value = None
        mock_repo_class.return_value = mock_repo

        event = {
            "ingestion_id": "ing-123",
            "document_id": "doc-456",
            "s3_key": "raw/ing-123/source.pdf",
        }

        with pytest.raises(ValidationPermanentError) as exc_info:
            await handler.__wrapped__(event, None)

        assert "Document not found" in str(exc_info.value)


class TestDuplicateDocumentError:
    """Tests for DuplicateDocumentError exception."""

    def test_error_attributes(self):
        error = DuplicateDocumentError(
            document_id="doc-new",
            existing_document_id="doc-existing",
            content_hash="abc123",
        )

        assert error.document_id == "doc-new"
        assert error.existing_document_id == "doc-existing"
        assert error.content_hash == "abc123"
        assert error.code == "DUPLICATE_DOCUMENT"
