# =============================================================================
# Vizonomy Infrastructure - Terraform Variables
# =============================================================================

# Basic Configuration
aws_region   = "us-east-1"
project_name = "vizonomy-v2"
environment  = "dev2"

# =============================================================================
# VPC Configuration
# =============================================================================
vpc_id = "vpc-0732b430d5e5f2cd2"
private_subnet_ids = [
  "subnet-0dab0219449d723a0", # us-east-1a
  "subnet-0a334c035832db6e2", # us-east-1b
  "subnet-0148ad18188682f43"  # us-east-1c
]

# CORS Allowed Origins
allowed_origins = [
  "https://app.vizonomy.com",
  "https://staging.vizonomy.com",
  "http://localhost:3000",
  "*" # Allow all for development
]

# =============================================================================
# EC2 Configuration (Microservices + PostgreSQL + Nginx)
# =============================================================================
ec2_instance_type = "t3.medium"

# SSH Key Pair - Create one in AWS Console if you don't have it
# AWS Console → EC2 → Key Pairs → Create Key Pair
ec2_key_pair_name = ""

# Network configuration
ec2_public_ip = true

# Storage
ec2_volume_size = 30

# Elastic IP for stable addressing
create_elastic_ip = true # Recommended so IP doesn't change on reboot

# SSH access - Open for development (use SSM Session Manager for better security)
ssh_allowed_cidrs = ["0.0.0.0/0"] # Open to all - use SSM instead for production

# VPC CIDR blocks for internal service access
vpc_cidr_blocks = ["172.31.0.0/16"]

# =============================================================================
# Database Configuration (runs on EC2)
# Two logical databases on same postgres instance:
# - housing: shared_data_layer (documents, chunks, knowledge graph)
# - auth_db: auth-service (users, tokens)
# =============================================================================
database_name      = "housing"
auth_database_name = "auth_db"
database_username  = "vizonomy_user"
database_password  = "iSQOjvXTBzJBcGCCt4koPDno"
database_port      = 5432

# Store credentials in AWS Secrets Manager
create_database_secret = true

# =============================================================================
# Git Repository (for EC2 deployment)
# =============================================================================
git_repo   = "https://github.com/VizonomyBO/housing-microservices.git"
git_branch = "master"
git_token  = "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"
