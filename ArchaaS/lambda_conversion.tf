# =============================================================================
# LAMBDA: Marker Converter (PDF to Markdown)
# =============================================================================
# This Lambda uses a container image since Marker requires ML models

# ECR Repository for Marker Converter
resource "aws_ecr_repository" "marker_converter" {
  name                 = "${var.project_name}-marker-converter-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "${var.project_name}-marker-converter-${var.environment}"
    Environment = var.environment
    Component   = "document-ingestion"
  }
}

# Note: The container image must be built and pushed to ECR before deploying the Lambda
# Use: docker build -t marker-converter ./lambdas/marker_converter
#      docker tag marker-converter:latest <account>.dkr.ecr.<region>.amazonaws.com/<repo>:latest
#      docker push <account>.dkr.ecr.<region>.amazonaws.com/<repo>:latest

# IAM Role for Marker Converter Lambda
resource "aws_iam_role" "marker_converter_lambda" {
  name = "${var.project_name}-marker-converter-lambda-${var.environment}"

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
    Name        = "${var.project_name}-marker-converter-lambda-${var.environment}"
    Environment = var.environment
  }
}

# IAM Policy for Marker Converter Lambda
resource "aws_iam_role_policy" "marker_converter_lambda" {
  name = "${var.project_name}-marker-converter-policy-${var.environment}"
  role = aws_iam_role.marker_converter_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:HeadObject"
        ]
        Resource = "${aws_s3_bucket.raw_documents.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.processed_artifacts.arn}/*"
      },
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

# Marker Converter Lambda Function (Container-based)
# NOTE: Uncomment this after pushing the container image to ECR
# resource "aws_lambda_function" "marker_converter" {
#   function_name = "${var.project_name}-marker-converter-${var.environment}"
#   role          = aws_iam_role.marker_converter_lambda.arn
#   package_type  = "Image"
#   image_uri     = "${aws_ecr_repository.marker_converter.repository_url}:latest"
#   
#   timeout     = 300  # 5 minutes for large PDFs
#   memory_size = 3008 # 3GB for ML models
#   
#   environment {
#     variables = {
#       RAW_DOCUMENTS_BUCKET = aws_s3_bucket.raw_documents.id
#       PROCESSED_BUCKET     = aws_s3_bucket.processed_artifacts.id
#       OPENAI_API_KEY       = var.openai_api_key  # For AI-powered footnotes
#       LOG_LEVEL            = var.log_level
#       ENVIRONMENT          = var.environment
#     }
#   }
#   
#   tracing_config {
#     mode = "Active"
#   }
#   
#   tags = {
#     Name        = "${var.project_name}-marker-converter-${var.environment}"
#     Environment = var.environment
#     Component   = "document-ingestion"
#   }
# }

# =============================================================================
# LAMBDA: Chunk Builder (Semantic Chunking)
# =============================================================================
# This Lambda is lightweight and can use a zip deployment

# Archive the chunk builder Lambda code
data "archive_file" "chunk_builder" {
  type        = "zip"
  source_dir  = "${path.module}/lambdas/chunk_builder"
  output_path = "${path.module}/lambdas/chunk_builder.zip"
  excludes    = ["tests", "__pycache__", "*.pyc", ".pytest_cache"]
}

# IAM Role for Chunk Builder Lambda
resource "aws_iam_role" "chunk_builder_lambda" {
  name = "${var.project_name}-chunk-builder-lambda-${var.environment}"

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
    Name        = "${var.project_name}-chunk-builder-lambda-${var.environment}"
    Environment = var.environment
  }
}

# IAM Policy for Chunk Builder Lambda
resource "aws_iam_role_policy" "chunk_builder_lambda" {
  name = "${var.project_name}-chunk-builder-policy-${var.environment}"
  role = aws_iam_role.chunk_builder_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.processed_artifacts.arn}/*"
      },
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

# Chunk Builder Lambda Function
resource "aws_lambda_function" "chunk_builder" {
  function_name    = "${var.project_name}-chunk-builder-${var.environment}"
  role             = aws_iam_role.chunk_builder_lambda.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.chunk_builder.output_path
  source_code_hash = data.archive_file.chunk_builder.output_base64sha256
  
  timeout     = 60
  memory_size = 512
  
  layers = [aws_lambda_layer_version.common_dependencies.arn]
  
  environment {
    variables = {
      PROCESSED_BUCKET     = aws_s3_bucket.processed_artifacts.id
      TARGET_CHUNK_TOKENS  = "500"
      MAX_CHUNK_TOKENS     = "1000"
      MIN_CHUNK_TOKENS     = "50"
      OVERLAP_TOKENS       = "50"
      LOG_LEVEL            = var.log_level
      ENVIRONMENT          = var.environment
    }
  }
  
  tracing_config {
    mode = "Active"
  }
  
  tags = {
    Name        = "${var.project_name}-chunk-builder-${var.environment}"
    Environment = var.environment
    Component   = "document-ingestion"
  }
}

# CloudWatch Log Group for Chunk Builder
resource "aws_cloudwatch_log_group" "chunk_builder" {
  name              = "/aws/lambda/${aws_lambda_function.chunk_builder.function_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-chunk-builder-logs-${var.environment}"
    Environment = var.environment
  }
}

# =============================================================================
# OUTPUTS
# =============================================================================

output "marker_converter_ecr_repository" {
  description = "ECR repository URL for Marker Converter"
  value       = aws_ecr_repository.marker_converter.repository_url
}

output "chunk_builder_lambda_arn" {
  description = "ARN of the Chunk Builder Lambda"
  value       = aws_lambda_function.chunk_builder.arn
}

output "chunk_builder_lambda_name" {
  description = "Name of the Chunk Builder Lambda"
  value       = aws_lambda_function.chunk_builder.function_name
}

