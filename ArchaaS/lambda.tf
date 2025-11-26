# Document Upload Lambda Function

# Archive the Lambda code (code only, deps in layer)
data "archive_file" "document_upload" {
  type        = "zip"
  source_dir  = "${path.module}/lambdas/document_upload"
  output_path = "${path.module}/dist/document_upload.zip"
  excludes    = ["tests", "__pycache__", "*.pyc", ".pytest_cache", "package", "requirements.txt", "pytest.ini"]
}

# Lambda function
resource "aws_lambda_function" "document_upload" {
  function_name = "${var.project_name}-document-upload-${var.environment}"
  description   = "Document Upload & Deduplication API - POST /v1/documents/upload"

  filename         = data.archive_file.document_upload.output_path
  source_code_hash = data.archive_file.document_upload.output_base64sha256

  runtime     = "python3.12"
  handler     = "handler.handler"
  timeout     = 30
  memory_size = 512

  role = aws_iam_role.document_upload_lambda.arn

  # Use shared Lambda layer for Python dependencies
  layers = [aws_lambda_layer_version.python_deps.arn]

  # VPC configuration for database access
  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      LOG_LEVEL                = var.log_level
      RAW_DOCUMENTS_BUCKET     = aws_s3_bucket.raw_documents.id
      S3_KEY_PREFIX            = "raw"
      PRESIGNED_URL_EXPIRY_SEC = var.presigned_url_expiry_sec
      MAX_FILE_SIZE_BYTES      = var.max_file_size_bytes
      # Use EC2-hosted PostgreSQL
      DATABASE_URL        = "postgresql://${var.database_username}:${var.database_password}@${aws_instance.microservices.private_ip}:${var.database_port}/${var.database_name}"
      DATABASE_HOST       = aws_instance.microservices.private_ip
      DATABASE_PORT       = var.database_port
      DATABASE_NAME       = var.database_name
      DATABASE_USER       = var.database_username
      DATABASE_SECRET_ARN = var.create_database_secret ? aws_secretsmanager_secret.database[0].arn : ""
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = {
    Name        = "${var.project_name}-document-upload"
    Environment = var.environment
    Service     = "document-upload"
  }

  depends_on = [
    aws_iam_role_policy_attachment.document_upload_basic,
    aws_iam_role_policy_attachment.document_upload_vpc,
    aws_iam_role_policy_attachment.document_upload_s3,
    aws_lambda_layer_version.python_deps,
  ]
}

# Lambda security group
resource "aws_security_group" "lambda" {
  name        = "${var.project_name}-lambda-sg-${var.environment}"
  description = "Security group for Lambda functions"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name        = "${var.project_name}-lambda-sg"
    Environment = var.environment
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "document_upload" {
  name              = "/aws/lambda/${aws_lambda_function.document_upload.function_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-document-upload-logs"
    Environment = var.environment
  }
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "document_upload_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.document_upload.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# Output Lambda details
output "document_upload_lambda_arn" {
  description = "ARN of the document upload Lambda function"
  value       = aws_lambda_function.document_upload.arn
}

output "document_upload_lambda_name" {
  description = "Name of the document upload Lambda function"
  value       = aws_lambda_function.document_upload.function_name
}

