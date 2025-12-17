# =============================================================================
# Consolidated Outputs for Vizonomy Infrastructure
# =============================================================================

output "summary" {
  description = "Summary of deployed resources"
  value = {
    s3 = {
      bucket_name = aws_s3_bucket.raw_documents.id
      bucket_arn  = aws_s3_bucket.raw_documents.arn
    }
    ec2 = {
      instance_id = aws_instance.microservices.id
      private_ip  = aws_instance.microservices.private_ip
      public_ip   = var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip
    }
    database = {
      host = aws_instance.microservices.private_ip
      port = var.database_port
      name = var.database_name
    }
  }
}

output "deployment_info" {
  description = "Deployment information"
  value = {
    environment = var.environment
    region      = var.aws_region
    project     = var.project_name
  }
}

output "service_endpoints" {
  description = "EC2-hosted service endpoints"
  value = {
    auth_service    = "http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:5001"
    user_service    = "http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:5002"
    agent_api       = "http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:8000"
    ingestion_api   = "http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:8085"
    postgres        = "${aws_instance.microservices.private_ip}:5432"
    public_hostname = var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip
  }
}

output "database_connection_info" {
  description = "Database connection information"
  sensitive   = true
  value = {
    host     = aws_instance.microservices.private_ip
    port     = var.database_port
    database = var.database_name
    username = var.database_username
    url      = "postgresql://${var.database_username}:${var.database_password}@${aws_instance.microservices.private_ip}:${var.database_port}/${var.database_name}"
  }
}

output "ec2_private_key_path" {
  description = "Local filesystem path for the generated EC2 SSH private key (empty when using a pre-existing key pair)."
  value       = local.ec2_generated_key_enabled ? local_sensitive_file.ec2_private_key[0].filename : ""
}

output "ec2_private_key_pem" {
  description = "Generated EC2 SSH private key PEM (sensitive). Empty when bringing your own key pair."
  sensitive   = true
  value       = local.ec2_generated_key_enabled ? tls_private_key.ec2_generated[0].private_key_pem : ""
}
