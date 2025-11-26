# Main configuration file for AWS resources
# Document Upload & Deduplication API Infrastructure

# Data sources for AWS account information
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Local values for resource naming
locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Output AWS account info
output "account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "caller_arn" {
  description = "ARN of the AWS caller"
  value       = data.aws_caller_identity.current.arn
}

output "region" {
  description = "AWS Region"
  value       = data.aws_region.current.name
}
