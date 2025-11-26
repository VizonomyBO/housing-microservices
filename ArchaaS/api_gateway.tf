# API Gateway HTTP API for Document Services

# HTTP API
resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api-${var.environment}"
  protocol_type = "HTTP"
  description   = "Vizonomy Document Services API"

  cors_configuration {
    allow_origins = [for origin in var.allowed_origins : origin if origin != "*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization", "X-Request-Id", "Idempotency-Key", "Viz-Request-Id"]
    expose_headers    = ["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"]
    max_age           = 3600
    allow_credentials = true
  }

  tags = {
    Name        = "${var.project_name}-api"
    Environment = var.environment
  }
}

# API Stage
resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = var.environment
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      httpMethod         = "$context.httpMethod"
      routeKey           = "$context.routeKey"
      status             = "$context.status"
      protocol           = "$context.protocol"
      responseLength     = "$context.responseLength"
      integrationError   = "$context.integrationErrorMessage"
      errorMessage       = "$context.error.message"
      authorizerError    = "$context.authorizer.error"
      integrationLatency = "$context.integrationLatency"
    })
  }

  default_route_settings {
    throttling_burst_limit = var.api_throttle_burst_limit
    throttling_rate_limit  = var.api_throttle_rate_limit
  }

  tags = {
    Name        = "${var.project_name}-api-stage"
    Environment = var.environment
  }
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-api-gateway-logs"
    Environment = var.environment
  }
}

# JWT Authorizer (connects to your auth service) - only created if issuer is configured
resource "aws_apigatewayv2_authorizer" "jwt" {
  count            = var.jwt_issuer != "" ? 1 : 0
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "jwt-authorizer"

  jwt_configuration {
    audience = var.jwt_audience
    issuer   = var.jwt_issuer
  }
}

# Document Upload Integration
resource "aws_apigatewayv2_integration" "document_upload" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.document_upload.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000

  request_parameters = {
    "overwrite:header.Viz-Request-Id" = "$context.requestId"
  }
}

# Document Upload Route
resource "aws_apigatewayv2_route" "document_upload" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /v1/documents/upload"
  target             = "integrations/${aws_apigatewayv2_integration.document_upload.id}"
  authorization_type = var.jwt_issuer != "" ? "JWT" : "NONE"
  authorizer_id      = var.jwt_issuer != "" ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

# Custom domain (optional)
resource "aws_apigatewayv2_domain_name" "main" {
  count       = var.custom_domain_name != "" ? 1 : 0
  domain_name = var.custom_domain_name

  domain_name_configuration {
    certificate_arn = var.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = {
    Name        = "${var.project_name}-api-domain"
    Environment = var.environment
  }
}

resource "aws_apigatewayv2_api_mapping" "main" {
  count       = var.custom_domain_name != "" ? 1 : 0
  api_id      = aws_apigatewayv2_api.main.id
  domain_name = aws_apigatewayv2_domain_name.main[0].id
  stage       = aws_apigatewayv2_stage.main.id
}

# Outputs
output "api_gateway_url" {
  description = "API Gateway invoke URL"
  value       = aws_apigatewayv2_stage.main.invoke_url
}

output "api_gateway_id" {
  description = "API Gateway ID"
  value       = aws_apigatewayv2_api.main.id
}

output "document_upload_endpoint" {
  description = "Document upload endpoint URL"
  value       = "${aws_apigatewayv2_stage.main.invoke_url}/v1/documents/upload"
}

