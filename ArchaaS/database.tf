# Database Configuration for EC2-hosted PostgreSQL
# This file configures database access and migrations

# Store database credentials in Secrets Manager (optional)
resource "aws_secretsmanager_secret" "database" {
  count       = var.create_database_secret ? 1 : 0
  name        = "${var.project_name}/database/${var.environment}"
  description = "Database credentials for ${var.project_name}"

  tags = {
    Name        = "${var.project_name}-database-secret"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret_version" "database" {
  count     = var.create_database_secret ? 1 : 0
  secret_id = aws_secretsmanager_secret.database[0].id
  secret_string = jsonencode({
    username = var.database_username
    password = var.database_password
    host     = aws_instance.microservices.private_ip
    port     = var.database_port
    dbname   = var.database_name
    url      = "postgresql://${var.database_username}:${var.database_password}@${aws_instance.microservices.private_ip}:${var.database_port}/${var.database_name}"
  })
}

# S3 bucket for migration files
resource "aws_s3_object" "database_migration" {
  bucket       = aws_s3_bucket.raw_documents.id
  key          = "migrations/001_create_documents_table.sql"
  source       = "${path.module}/migrations/001_create_documents_table.sql"
  content_type = "text/plain"
  etag         = filemd5("${path.module}/migrations/001_create_documents_table.sql")

  tags = {
    Name        = "Database migration"
    Environment = var.environment
  }
}

# =============================================================================
# EC2 CONFIG FILES (uploaded to S3)
# =============================================================================

resource "aws_s3_object" "docker_compose" {
  bucket       = aws_s3_bucket.raw_documents.id
  key          = "configs/docker-compose.yml"
  source       = "${path.module}/../docker-compose.ec2.yml"
  content_type = "text/yaml"
  etag         = filemd5("${path.module}/../docker-compose.ec2.yml")
}

# Output database connection info
output "database_url" {
  description = "PostgreSQL connection URL (uses EC2 private IP)"
  value       = "postgresql://${var.database_username}:****@${aws_instance.microservices.private_ip}:${var.database_port}/${var.database_name}"
  sensitive   = true
}

output "database_host_ec2" {
  description = "Database host (EC2 private IP)"
  value       = aws_instance.microservices.private_ip
}

output "database_secret_arn" {
  description = "ARN of database credentials secret"
  value       = var.create_database_secret ? aws_secretsmanager_secret.database[0].arn : ""
}

output "migration_s3_uri" {
  description = "S3 URI for the database migration file"
  value       = "s3://${aws_s3_bucket.raw_documents.id}/migrations/001_create_documents_table.sql"
}
