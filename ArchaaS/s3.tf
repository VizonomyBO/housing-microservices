# Random suffix for unique bucket names
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# S3 Bucket for raw document storage
# Stores uploaded documents before processing

resource "aws_s3_bucket" "raw_documents" {
  bucket = "${var.project_name}-raw-docs-${var.environment}-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "${var.project_name}-raw-documents"
    Environment = var.environment
    Purpose     = "Document storage for upload processing"
  }
}

# Enable versioning for document integrity
resource "aws_s3_bucket_versioning" "raw_documents" {
  bucket = aws_s3_bucket.raw_documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption for security
resource "aws_s3_bucket_server_side_encryption_configuration" "raw_documents" {
  bucket = aws_s3_bucket.raw_documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "raw_documents" {
  bucket = aws_s3_bucket.raw_documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle rules for cost optimization
resource "aws_s3_bucket_lifecycle_configuration" "raw_documents" {
  bucket = aws_s3_bucket.raw_documents.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    expiration {
      days = 365
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# CORS configuration for browser-based uploads
resource "aws_s3_bucket_cors_configuration" "raw_documents" {
  bucket = aws_s3_bucket.raw_documents.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST"]
    allowed_origins = var.allowed_origins
    expose_headers  = ["ETag", "x-amz-meta-content-hash"]
    max_age_seconds = 3600
  }
}

# S3 notification to trigger preflight Lambda on new uploads
resource "aws_s3_bucket_notification" "raw_documents" {
  bucket = aws_s3_bucket.raw_documents.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.preflight_validator.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/"
  }

  depends_on = [aws_lambda_permission.s3_preflight_trigger]
}

# Permission for S3 to invoke preflight Lambda
resource "aws_lambda_permission" "s3_preflight_trigger" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.preflight_validator.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw_documents.arn
}

# Output bucket details
output "raw_documents_bucket_name" {
  description = "Name of the raw documents S3 bucket"
  value       = aws_s3_bucket.raw_documents.id
}

output "raw_documents_bucket_arn" {
  description = "ARN of the raw documents S3 bucket"
  value       = aws_s3_bucket.raw_documents.arn
}

