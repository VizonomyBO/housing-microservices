# Lambda Layer for Python Dependencies
# Shared layer for document processing Lambdas
#
# PREREQUISITE: Run scripts/build_lambda_layer.sh before terraform apply
# This builds the layer using Docker with Lambda Python 3.12 runtime

# Check if layer exists
locals {
  layer_zip_path = "${path.module}/lambdas/layer.zip"
  layer_exists   = fileexists(local.layer_zip_path)
}

# Lambda Layer
resource "aws_lambda_layer_version" "python_deps" {
  filename            = local.layer_zip_path
  layer_name          = "${var.project_name}-python-deps-${var.environment}"
  description         = "Python dependencies for document processing Lambdas (aioboto3, asyncpg, pydantic)"
  compatible_runtimes = ["python3.12"]
  source_code_hash    = local.layer_exists ? filebase64sha256(local.layer_zip_path) : ""

  lifecycle {
    create_before_destroy = true
  }
}

# Output
output "lambda_layer_arn" {
  description = "ARN of the Python dependencies Lambda layer"
  value       = aws_lambda_layer_version.python_deps.arn
}

