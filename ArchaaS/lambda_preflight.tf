# Preflight Validator Lambda Function
# Step Function: DocumentIngestionStateMachine -> Preflight State

# Build preflight validator with common module
resource "null_resource" "preflight_validator_package" {
  triggers = {
    handler_hash = filemd5("${path.module}/lambdas/preflight_validator/handler.py")
    common_hash  = filemd5("${path.module}/lambdas/common/__init__.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      rm -rf ${path.module}/dist/preflight_pkg
      mkdir -p ${path.module}/dist/preflight_pkg
      cp -r ${path.module}/lambdas/preflight_validator/* ${path.module}/dist/preflight_pkg/
      cp -r ${path.module}/lambdas/common ${path.module}/dist/preflight_pkg/
      rm -rf ${path.module}/dist/preflight_pkg/tests
      rm -rf ${path.module}/dist/preflight_pkg/__pycache__
      find ${path.module}/dist/preflight_pkg -name "*.pyc" -delete
    EOT
  }
}

# Archive the Lambda code (code + common module, deps in layer)
data "archive_file" "preflight_validator" {
  type        = "zip"
  source_dir  = "${path.module}/dist/preflight_pkg"
  output_path = "${path.module}/dist/preflight_validator.zip"
  excludes    = ["tests", "__pycache__", "*.pyc", ".pytest_cache", "package", "requirements.txt", "pytest.ini"]

  depends_on = [null_resource.preflight_validator_package]
}

# Lambda function
resource "aws_lambda_function" "preflight_validator" {
  function_name = "${var.project_name}-preflight-validator-${var.environment}"
  description   = "Preflight Validation - MIME type, deduplication, artifact placeholders"

  filename         = data.archive_file.preflight_validator.output_path
  source_code_hash = data.archive_file.preflight_validator.output_base64sha256

  runtime     = "python3.12"
  handler     = "handler.handler"
  timeout     = 60  # Longer timeout for S3 operations and hash computation
  memory_size = 1024  # More memory for file processing

  role = aws_iam_role.preflight_validator_lambda.arn

  # Use shared Lambda layers for Python dependencies and shared data layer
  layers = [
    aws_lambda_layer_version.python_deps.arn,
    aws_lambda_layer_version.shared_data_layer.arn
  ]

  # NOTE: Not using VPC to allow S3 access without VPC endpoint
  # Database accessed via public IP with security group allowing port 5432

  environment {
    variables = {
      ENVIRONMENT                = var.environment
      LOG_LEVEL                  = var.log_level
      RAW_DOCUMENTS_BUCKET       = aws_s3_bucket.raw_documents.id
      PROCESSED_ARTIFACTS_BUCKET = aws_s3_bucket.processed_artifacts.id
      MAX_FILE_SIZE_BYTES        = var.max_file_size_bytes
      # Step Function for document processing
      STEP_FUNCTION_ARN          = aws_sfn_state_machine.document_ingestion.arn
      # EventBridge for progress events
      EVENT_BUS_NAME             = aws_cloudwatch_event_bus.ingestion.name
      # Database connection (using public IP - EC2 SG allows 5432 from 0.0.0.0/0)
      DATABASE_URL               = "postgresql://${var.database_username}:${var.database_password}@${aws_instance.microservices.public_ip}:${var.database_port}/${var.database_name}"
      DATABASE_HOST              = aws_instance.microservices.public_ip
      DATABASE_PORT              = var.database_port
      DATABASE_NAME              = var.database_name
      DATABASE_USER              = var.database_username
      DATABASE_PASSWORD          = var.database_password
      DATABASE_SECRET_ARN        = var.create_database_secret ? aws_secretsmanager_secret.database[0].arn : ""
      # Marker service for PDF conversion (runs on EC2)
      MARKER_SERVICE_URL         = "http://${aws_instance.microservices.public_ip}:8004"
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = {
    Name        = "${var.project_name}-preflight-validator"
    Environment = var.environment
    Service     = "ingestion-pipeline"
    Stage       = "preflight"
  }

  depends_on = [
    aws_iam_role_policy_attachment.preflight_validator_basic,
    aws_iam_role_policy_attachment.preflight_validator_vpc,
    aws_lambda_layer_version.python_deps,
  ]
}

# S3 Bucket for processed artifacts (if not exists)
resource "aws_s3_bucket" "processed_artifacts" {
  bucket = "${var.project_name}-processed-artifacts-${var.environment}-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "${var.project_name}-processed-artifacts"
    Environment = var.environment
    Purpose     = "Processed-artifacts-storage"
  }
}

# Enable versioning for processed artifacts
resource "aws_s3_bucket_versioning" "processed_artifacts" {
  bucket = aws_s3_bucket.processed_artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption for processed artifacts
resource "aws_s3_bucket_server_side_encryption_configuration" "processed_artifacts" {
  bucket = aws_s3_bucket.processed_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Block public access for processed artifacts
resource "aws_s3_bucket_public_access_block" "processed_artifacts" {
  bucket = aws_s3_bucket.processed_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# IAM Role for Preflight Validator Lambda
resource "aws_iam_role" "preflight_validator_lambda" {
  name = "${var.project_name}-preflight-validator-role-${var.environment}"

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
    Name        = "${var.project_name}-preflight-validator-role"
    Environment = var.environment
  }
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "preflight_validator_basic" {
  role       = aws_iam_role.preflight_validator_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# VPC access policy
resource "aws_iam_role_policy_attachment" "preflight_validator_vpc" {
  role       = aws_iam_role.preflight_validator_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# S3 access policy for preflight validator
resource "aws_iam_role_policy" "preflight_validator_s3" {
  name = "${var.project_name}-preflight-validator-s3-policy"
  role = aws_iam_role.preflight_validator_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:HeadObject",
          "s3:DeleteObject"  # For deleting duplicate files
        ]
        Resource = [
          "${aws_s3_bucket.raw_documents.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:HeadObject"
        ]
        Resource = [
          "${aws_s3_bucket.processed_artifacts.arn}/*"
        ]
      }
    ]
  })
}

# Step Functions policy for preflight validator
resource "aws_iam_role_policy" "preflight_validator_stepfunctions" {
  name = "${var.project_name}-preflight-validator-sfn-policy"
  role = aws_iam_role.preflight_validator_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "states:StartExecution"
        ]
        Resource = [
          aws_sfn_state_machine.document_ingestion.arn
        ]
      }
    ]
  })
}

# X-Ray tracing policy
resource "aws_iam_role_policy" "preflight_validator_xray" {
  name = "${var.project_name}-preflight-validator-xray-policy"
  role = aws_iam_role.preflight_validator_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
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

# EventBridge policy for progress events
resource "aws_iam_role_policy" "preflight_validator_eventbridge" {
  name = "${var.project_name}-preflight-validator-eventbridge-policy"
  role = aws_iam_role.preflight_validator_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "events:PutEvents"
        ]
        Resource = [
          aws_cloudwatch_event_bus.ingestion.arn
        ]
      }
    ]
  })
}

# CloudWatch Log Group for Preflight Validator
resource "aws_cloudwatch_log_group" "preflight_validator" {
  name              = "/aws/lambda/${aws_lambda_function.preflight_validator.function_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-preflight-validator-logs"
    Environment = var.environment
  }
}

# Outputs
output "preflight_validator_lambda_arn" {
  description = "ARN of the preflight validator Lambda function"
  value       = aws_lambda_function.preflight_validator.arn
}

output "preflight_validator_lambda_name" {
  description = "Name of the preflight validator Lambda function"
  value       = aws_lambda_function.preflight_validator.function_name
}

output "processed_artifacts_bucket_name" {
  description = "Name of the processed artifacts S3 bucket"
  value       = aws_s3_bucket.processed_artifacts.id
}

output "processed_artifacts_bucket_arn" {
  description = "ARN of the processed artifacts S3 bucket"
  value       = aws_s3_bucket.processed_artifacts.arn
}

