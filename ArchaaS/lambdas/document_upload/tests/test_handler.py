"""
Unit tests for document upload Lambda handler.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

# Mock environment variables before importing handler
import os
os.environ["RAW_DOCUMENTS_BUCKET"] = "test-bucket"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"

from handler import (
    DocumentUploadRequest,
    DocumentUploadResponse,
    create_error_response,
    create_success_response,
    handler,
    ALLOWED_SOURCE_TYPES,
    MAX_FILE_SIZE_BYTES,
)


class TestDocumentUploadRequest:
    """Tests for request validation."""
    
    def test_valid_request(self):
        """Test valid request parsing."""
        data = {
            "document_name": "test.pdf",
            "source_type": "pdf",
            "country_code": "USA",
            "file_size_bytes": 1024,
        }
        request = DocumentUploadRequest(**data)
        assert request.document_name == "test.pdf"
        assert request.source_type == "pdf"
        assert request.access_scope == "user_private"
    
    def test_invalid_source_type(self):
        """Test rejection of invalid source types."""
        data = {
            "document_name": "test.exe",
            "source_type": "exe",
            "country_code": "USA",
            "file_size_bytes": 1024,
        }
        with pytest.raises(ValueError, match="Invalid source_type"):
            DocumentUploadRequest(**data)
    
    def test_file_size_exceeds_limit(self):
        """Test rejection of files exceeding size limit."""
        data = {
            "document_name": "large.pdf",
            "source_type": "pdf",
            "country_code": "USA",
            "file_size_bytes": MAX_FILE_SIZE_BYTES + 1,
        }
        with pytest.raises(ValueError, match="exceeds limit"):
            DocumentUploadRequest(**data)
    
    def test_zero_file_size(self):
        """Test rejection of zero file size."""
        data = {
            "document_name": "empty.pdf",
            "source_type": "pdf",
            "country_code": "USA",
            "file_size_bytes": 0,
        }
        with pytest.raises(ValueError, match="must be positive"):
            DocumentUploadRequest(**data)
    
    def test_invalid_access_scope(self):
        """Test rejection of invalid access scope."""
        data = {
            "document_name": "test.pdf",
            "source_type": "pdf",
            "country_code": "USA",
            "file_size_bytes": 1024,
            "access_scope": "invalid",
        }
        with pytest.raises(ValueError, match="Invalid access_scope"):
            DocumentUploadRequest(**data)
    
    def test_content_hash_validation(self):
        """Test content hash validation (must be valid hex)."""
        data = {
            "document_name": "test.pdf",
            "source_type": "pdf",
            "country_code": "USA",
            "file_size_bytes": 1024,
            "content_hash": "not-a-valid-hex-string-at-all-definitely-invalid",
        }
        with pytest.raises(ValueError, match="valid hexadecimal"):
            DocumentUploadRequest(**data)
    
    def test_valid_content_hash(self):
        """Test valid SHA-256 content hash is preserved exactly."""
        valid_hash = "a" * 64  # Valid 64-char hex string
        data = {
            "document_name": "test.pdf",
            "source_type": "pdf",
            "country_code": "USA",
            "file_size_bytes": 1024,
            "content_hash": valid_hash,
        }
        request = DocumentUploadRequest(**data)
        # Ensure hash is stored exactly as provided
        assert request.content_hash == valid_hash
    
    def test_all_source_types_allowed(self):
        """Test all allowed source types."""
        for source_type in ALLOWED_SOURCE_TYPES.keys():
            data = {
                "document_name": f"test.{source_type}",
                "source_type": source_type,
                "country_code": "USA",
                "file_size_bytes": 1024,
            }
            request = DocumentUploadRequest(**data)
            assert request.source_type == source_type


class TestErrorResponse:
    """Tests for error response formatting."""
    
    def test_error_response_structure(self):
        """Test error response follows API contract."""
        response = create_error_response(
            status_code=400,
            error_code="VALIDATION_ERROR",
            message="Invalid request",
            request_id="test-123",
            details={"field": "source_type"},
        )
        
        assert response["statusCode"] == 400
        assert "application/json" in response["headers"]["Content-Type"]
        
        body = json.loads(response["body"])
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["message"] == "Invalid request"
        assert body["error"]["request_id"] == "test-123"
        assert body["error"]["details"]["field"] == "source_type"
    
    def test_error_response_with_retry_after(self):
        """Test error response with retry_after_sec."""
        response = create_error_response(
            status_code=429,
            error_code="RATE_LIMITED",
            message="Too many requests",
            request_id="test-123",
            retry_after_sec=60,
        )
        
        body = json.loads(response["body"])
        assert body["error"]["retry_after_sec"] == 60


class TestSuccessResponse:
    """Tests for success response formatting."""
    
    def test_success_response_structure(self):
        """Test success response structure."""
        response = create_success_response(
            status_code=201,
            body={"document_id": "doc_123"},
            request_id="test-123",
        )
        
        assert response["statusCode"] == 201
        assert response["headers"]["X-Request-Id"] == "test-123"
        
        body = json.loads(response["body"])
        assert body["document_id"] == "doc_123"


class TestHandlerIntegration:
    """Integration tests for the Lambda handler."""
    
    @pytest.fixture
    def valid_event(self):
        """Create a valid Lambda event."""
        return {
            "requestContext": {
                "requestId": "test-request-id",
                "authorizer": {
                    "claims": {
                        "sub": "user-123",
                        "roles": ["user"],
                    }
                }
            },
            "headers": {},
            "body": json.dumps({
                "document_name": "test-document.pdf",
                "source_type": "pdf",
                "country_code": "USA",
                "language": "en",
                "file_size_bytes": 5242880,
                "content_hash": "a" * 64,
            }),
        }
    
    @pytest.mark.asyncio
    @patch("handler.DocumentRepository")
    @patch("handler.generate_presigned_url")
    async def test_new_document_upload(self, mock_presigned, mock_repo_class, valid_event):
        """Test successful new document upload."""
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.find_by_owner_and_hash.return_value = None
        mock_repo.create_document.return_value = {"id": "doc_test123"}
        mock_repo_class.return_value = mock_repo
        
        mock_presigned.return_value = {
            "url": "https://s3.amazonaws.com/test-bucket/...",
            "fields": {"key": "raw/ing-xxx/source.pdf"},
            "expires_in_sec": 900,
        }
        
        # Import the actual async handler
        from handler import handler as sync_handler
        import asyncio
        
        # The handler is wrapped with @async_handler, so it runs synchronously
        response = sync_handler(valid_event, None)
        
        assert response["statusCode"] == 201
        body = json.loads(response["body"])
        assert body["status"] == "PENDING_UPLOAD"
        assert body["upload"] is not None
        assert "url" in body["upload"]
    
    @pytest.mark.asyncio
    @patch("handler.DocumentRepository")
    async def test_deduplication(self, mock_repo_class, valid_event):
        """Test deduplication returns existing document."""
        # Setup mock to return existing document
        existing_doc = {
            "id": "doc_existing",
            "content_hash": "a" * 64,
            "access_scope": "user_private",
        }
        mock_repo = AsyncMock()
        mock_repo.find_by_owner_and_hash.return_value = existing_doc
        mock_repo_class.return_value = mock_repo
        
        from handler import handler as sync_handler
        
        response = sync_handler(valid_event, None)
        
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "DEDUPED"
        assert body["document_id"] == "doc_existing"
        assert body["deduped_from"] == "doc_existing"
        assert body["upload"] is None
        assert body["ingestion_id"] is None
    
    def test_missing_authorization(self):
        """Test handling of missing authorization."""
        event = {
            "requestContext": {"requestId": "test-123"},
            "headers": {},
            "body": json.dumps({
                "document_name": "test.pdf",
                "source_type": "pdf",
                "country_code": "USA",
                "file_size_bytes": 1024,
            }),
        }
        
        from handler import handler as sync_handler
        response = sync_handler(event, None)
        
        assert response["statusCode"] == 401
    
    def test_invalid_json_body(self):
        """Test handling of invalid JSON body."""
        event = {
            "requestContext": {
                "requestId": "test-123",
                "authorizer": {"claims": {"sub": "user-123"}},
            },
            "headers": {},
            "body": "not valid json",
        }
        
        from handler import handler as sync_handler
        response = sync_handler(event, None)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
    
    def test_base_scope_requires_admin(self):
        """Test that base scope requires admin role."""
        event = {
            "requestContext": {
                "requestId": "test-123",
                "authorizer": {
                    "claims": {
                        "sub": "user-123",
                        "roles": ["user"],  # Not admin
                    }
                },
            },
            "headers": {},
            "body": json.dumps({
                "document_name": "base-doc.pdf",
                "source_type": "pdf",
                "country_code": "USA",
                "file_size_bytes": 1024,
                "access_scope": "base",
            }),
        }
        
        from handler import handler as sync_handler
        response = sync_handler(event, None)
        
        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error"]["code"] == "FORBIDDEN"


class TestContentHashPreservation:
    """Tests ensuring content_hash is preserved exactly as provided."""
    
    def test_hash_preserved_in_request(self):
        """Ensure content_hash is not modified during validation."""
        # Test various valid hex formats
        test_hashes = [
            "79ce5ec2f1a41f9a7f6e5f8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d",
            "ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789",
            "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        ]
        
        for original_hash in test_hashes:
            data = {
                "document_name": "test.pdf",
                "source_type": "pdf",
                "country_code": "USA",
                "file_size_bytes": 1024,
                "content_hash": original_hash,
            }
            request = DocumentUploadRequest(**data)
            # Hash should be exactly as provided, no case normalization
            assert request.content_hash == original_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

