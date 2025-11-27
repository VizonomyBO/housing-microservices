# Document Ingestion Step Function

# Step Function State Machine
resource "aws_sfn_state_machine" "document_ingestion" {
  name     = "${var.project_name}-document-ingestion-${var.environment}"
  role_arn = aws_iam_role.step_function.arn

  definition = templatefile("${path.module}/step_functions/document_ingestion_workflow.asl.json", {
    # NOTE: Preflight validation now runs via S3 trigger BEFORE this Step Function starts
    MarkerConverterLambdaArn     = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-marker-converter-${var.environment}"
    ChunkBuilderLambdaArn        = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-chunk-builder-${var.environment}"
    TableNormalizerLambdaArn     = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-table-normalizer-${var.environment}"
    FigureCaptionerLambdaArn     = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-figure-captioner-${var.environment}"
    EmbeddingWriterLambdaArn     = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-embedding-writer-${var.environment}"
    IngestionFinalizerLambdaArn  = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-ingestion-finalizer-${var.environment}"
    EventBusName                 = aws_cloudwatch_event_bus.ingestion.name
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_function.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = {
    Name        = "${var.project_name}-document-ingestion"
    Environment = var.environment
    Service     = "ingestion-pipeline"
  }
}

# CloudWatch Log Group for Step Function
resource "aws_cloudwatch_log_group" "step_function" {
  name              = "/aws/vendedlogs/states/${var.project_name}-document-ingestion-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-step-function-logs"
    Environment = var.environment
  }
}

# EventBridge Custom Event Bus for ingestion events
resource "aws_cloudwatch_event_bus" "ingestion" {
  name = "${var.project_name}-ingestion-events-${var.environment}"

  tags = {
    Name        = "${var.project_name}-ingestion-events"
    Environment = var.environment
  }
}

# IAM Role for Step Function
resource "aws_iam_role" "step_function" {
  name = "${var.project_name}-step-function-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-step-function-role"
    Environment = var.environment
  }
}

# IAM Policy for Step Function to invoke Lambdas
resource "aws_iam_role_policy" "step_function_lambda" {
  name = "${var.project_name}-step-function-lambda-policy"
  role = aws_iam_role.step_function.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          # Preflight Lambda is now triggered by S3, not Step Functions
          "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-*-${var.environment}"
        ]
      }
    ]
  })
}

# IAM Policy for Step Function to publish to EventBridge
resource "aws_iam_role_policy" "step_function_events" {
  name = "${var.project_name}-step-function-events-policy"
  role = aws_iam_role.step_function.id

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

# IAM Policy for Step Function logging
resource "aws_iam_role_policy" "step_function_logging" {
  name = "${var.project_name}-step-function-logging-policy"
  role = aws_iam_role.step_function.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutLogEvents",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM Policy for X-Ray tracing
resource "aws_iam_role_policy" "step_function_xray" {
  name = "${var.project_name}-step-function-xray-policy"
  role = aws_iam_role.step_function.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets"
        ]
        Resource = "*"
      }
    ]
  })
}

# EventBridge Rule to trigger Step Function from S3 events
resource "aws_cloudwatch_event_rule" "s3_upload_trigger" {
  name        = "${var.project_name}-s3-upload-trigger-${var.environment}"
  description = "Triggers ingestion pipeline when documents are uploaded to S3"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [aws_s3_bucket.raw_documents.id]
      }
      object = {
        key = [{
          prefix = "raw/"
        }]
      }
    }
  })

  tags = {
    Name        = "${var.project_name}-s3-upload-trigger"
    Environment = var.environment
  }
}

# EventBridge Target - Step Function
resource "aws_cloudwatch_event_target" "step_function" {
  rule      = aws_cloudwatch_event_rule.s3_upload_trigger.name
  target_id = "DocumentIngestionStateMachine"
  arn       = aws_sfn_state_machine.document_ingestion.arn
  role_arn  = aws_iam_role.eventbridge_sfn.arn

  # Transform S3 event to Step Function input
  input_transformer {
    input_paths = {
      s3_bucket = "$.detail.bucket.name"
      s3_key    = "$.detail.object.key"
      etag      = "$.detail.object.etag"
      time      = "$.time"
    }
    input_template = <<EOF
{
  "ingestion_id": <s3_key>,
  "s3_bucket": <s3_bucket>,
  "s3_key": <s3_key>,
  "trace_id": "trace-<etag>",
  "timestamps": {
    "uploaded_at": <time>
  },
  "retries": {
    "preflight": 0,
    "convert": 0,
    "chunk": 0,
    "embed": 0
  }
}
EOF
  }
}

# IAM Role for EventBridge to start Step Function
resource "aws_iam_role" "eventbridge_sfn" {
  name = "${var.project_name}-eventbridge-sfn-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-eventbridge-sfn-role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "eventbridge_sfn" {
  name = "${var.project_name}-eventbridge-sfn-policy"
  role = aws_iam_role.eventbridge_sfn.id

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

# Outputs
output "step_function_arn" {
  description = "ARN of the document ingestion Step Function"
  value       = aws_sfn_state_machine.document_ingestion.arn
}

output "step_function_name" {
  description = "Name of the document ingestion Step Function"
  value       = aws_sfn_state_machine.document_ingestion.name
}

output "ingestion_event_bus_name" {
  description = "Name of the ingestion EventBridge event bus"
  value       = aws_cloudwatch_event_bus.ingestion.name
}

