# =============================================================================
# Consolidated Outputs for Vizonomy Infrastructure
# =============================================================================

output "summary" {
  description = "Summary of deployed resources"
  value = {
    api = {
      gateway_url     = aws_apigatewayv2_stage.main.invoke_url
      upload_endpoint = "${aws_apigatewayv2_stage.main.invoke_url}/v1/documents/upload"
    }
    lambda = {
      function_name = aws_lambda_function.document_upload.function_name
      function_arn  = aws_lambda_function.document_upload.arn
    }
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

# =============================================================================
# Service Endpoints
# =============================================================================

output "service_endpoints" {
  description = "All service endpoints"
  value = {
    api_gateway  = aws_apigatewayv2_stage.main.invoke_url
    auth_service = "http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:5001"
    user_service = "http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:5002"
    swagger      = "http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:3000"
    postgres     = "${aws_instance.microservices.private_ip}:5432"
  }
}

# =============================================================================
# Connection Strings (Sensitive)
# =============================================================================

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

# =============================================================================
# Quick Start Commands
# =============================================================================

output "quick_start" {
  description = "Quick start commands after deployment"
  sensitive   = true
  value       = <<-EOT
    
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                         VIZONOMY DEPLOYMENT COMPLETE                         ║
    ╚══════════════════════════════════════════════════════════════════════════════╝

    📦 EC2 Instance: ${aws_instance.microservices.id}
    🌐 Public IP: ${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}
    🔒 Private IP: ${aws_instance.microservices.private_ip}

    ────────────────────────────────────────────────────────────────────────────────
    SSH into EC2:
    ────────────────────────────────────────────────────────────────────────────────
    ssh -i ~/.ssh/${var.ec2_key_pair_name}.pem ec2-user@${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}

    ────────────────────────────────────────────────────────────────────────────────
    Run Database Migration (on EC2):
    ────────────────────────────────────────────────────────────────────────────────
    # Download migration from S3
    aws s3 cp s3://${aws_s3_bucket.raw_documents.id}/migrations/001_create_documents_table.sql /opt/vizonomy/migrations/

    # Run migration
    docker exec -i vizonomy-postgres psql -U ${var.database_username} -d ${var.database_name} < /opt/vizonomy/migrations/001_create_documents_table.sql

    ────────────────────────────────────────────────────────────────────────────────
    Deploy Microservices:
    ────────────────────────────────────────────────────────────────────────────────
    /opt/vizonomy/deploy.sh

    ────────────────────────────────────────────────────────────────────────────────
    Service URLs:
    ────────────────────────────────────────────────────────────────────────────────
    🚀 API Gateway:    ${aws_apigatewayv2_stage.main.invoke_url}
    📄 Upload Endpoint: ${aws_apigatewayv2_stage.main.invoke_url}/v1/documents/upload
    🔐 Auth Service:   http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:5001
    👤 User Service:   http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:5002
    📚 Swagger:        http://${var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip}:3000

    ────────────────────────────────────────────────────────────────────────────────
    Test Document Upload:
    ────────────────────────────────────────────────────────────────────────────────
    curl -X POST ${aws_apigatewayv2_stage.main.invoke_url}/v1/documents/upload \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer YOUR_JWT_TOKEN" \
      -d '{
        "document_name": "test.pdf",
        "source_type": "pdf",
        "country_code": "USA",
        "file_size_bytes": 1024
      }'
    
  EOT
}
