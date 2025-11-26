# IAM Roles and Policies for Document Upload Lambda

# Lambda execution role
resource "aws_iam_role" "document_upload_lambda" {
  name = "${var.project_name}-document-upload-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-document-upload-lambda"
    Environment = var.environment
  }
}

# Basic Lambda execution policy (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "document_upload_basic" {
  role       = aws_iam_role.document_upload_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# VPC execution policy (for database access)
resource "aws_iam_role_policy_attachment" "document_upload_vpc" {
  role       = aws_iam_role.document_upload_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# S3 policy for presigned URL generation and object operations
resource "aws_iam_policy" "document_upload_s3" {
  name        = "${var.project_name}-document-upload-s3-${var.environment}"
  description = "S3 permissions for document upload Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowPresignedUrlGeneration"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.raw_documents.arn}/*"
      },
      {
        Sid    = "AllowBucketListing"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.raw_documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "document_upload_s3" {
  role       = aws_iam_role.document_upload_lambda.name
  policy_arn = aws_iam_policy.document_upload_s3.arn
}

# Secrets Manager policy for database credentials
resource "aws_iam_policy" "document_upload_secrets" {
  count       = var.create_database_secret ? 1 : 0
  name        = "${var.project_name}-document-upload-secrets-${var.environment}"
  description = "Secrets Manager permissions for document upload Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSecretsAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.database[0].arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "document_upload_secrets" {
  count      = var.create_database_secret ? 1 : 0
  role       = aws_iam_role.document_upload_lambda.name
  policy_arn = aws_iam_policy.document_upload_secrets[0].arn
}

# X-Ray tracing policy
resource "aws_iam_policy" "document_upload_xray" {
  name        = "${var.project_name}-document-upload-xray-${var.environment}"
  description = "X-Ray tracing permissions for document upload Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowXRayTracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "document_upload_xray" {
  role       = aws_iam_role.document_upload_lambda.name
  policy_arn = aws_iam_policy.document_upload_xray.arn
}

# Output role ARN
output "document_upload_lambda_role_arn" {
  description = "ARN of the document upload Lambda execution role"
  value       = aws_iam_role.document_upload_lambda.arn
}

