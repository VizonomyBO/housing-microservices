# =============================================================================
# LAMBDA LAYER: Shared Data Layer
# =============================================================================
# Contains:
# - shared_data_layer package (SQLAlchemy models, repositories, schemas)
# - Database dependencies (asyncpg, sqlalchemy)
# - MIME detection (python-magic)
# - EventBridge helpers

resource "aws_lambda_layer_version" "shared_data_layer" {
  layer_name          = "${var.project_name}-shared-data-layer-${var.environment}"
  description         = "Shared data layer with SQLAlchemy models, repositories, and database access"
  filename            = "${path.module}/lambdas/shared_layer.zip"
  source_code_hash    = fileexists("${path.module}/lambdas/shared_layer.zip") ? filebase64sha256("${path.module}/lambdas/shared_layer.zip") : null
  compatible_runtimes = ["python3.12"]

  lifecycle {
    create_before_destroy = true
  }
}

output "shared_data_layer_arn" {
  description = "ARN of the shared data layer Lambda layer"
  value       = aws_lambda_layer_version.shared_data_layer.arn
}

