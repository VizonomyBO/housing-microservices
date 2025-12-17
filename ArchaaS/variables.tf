variable "aws_region" {
  description = "AWS Region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "vizonomy"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# VPC Configuration
variable "vpc_id" {
  description = "VPC ID for EC2 deployment"
  type        = string
  default     = ""
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for EC2 networking (used for security groups/EIP)"
  type        = list(string)
  default     = []
}

# S3 Configuration
variable "allowed_origins" {
  description = "Allowed origins for CORS (S3/object storage)"
  type        = list(string)
  default     = ["https://*.vizonomy.com", "http://localhost:3000"]
}

variable "ses_domain" {
  description = "Domain to verify for SES sending (leave blank to skip)"
  type        = string
  default     = ""
}

variable "ses_from_email" {
  description = "From email address for SES (should match the verified domain)"
  type        = string
  default     = ""
}

variable "ses_configuration_set_name" {
  description = "Optional SES configuration set name (leave blank to skip creation)"
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# Database Configuration
variable "database_url" {
  description = "PostgreSQL database connection URL"
  type        = string
  default     = ""
  sensitive   = true
}

variable "database_secret_arn" {
  description = "ARN of the Secrets Manager secret containing database credentials"
  type        = string
  default     = ""
}

variable "database_security_group_id" {
  description = "Security group ID of the RDS instance"
  type        = string
  default     = ""
}

variable "create_database_secret" {
  description = "Whether to create database secret in Secrets Manager"
  type        = bool
  default     = false
}

variable "database_username" {
  description = "Database username"
  type        = string
  default     = "vizonomy_user"
  sensitive   = true
}

variable "database_password" {
  description = "Database password (used if create_database_secret is true)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "database_host" {
  description = "Database host (used if create_database_secret is true)"
  type        = string
  default     = "localhost"
}

variable "database_port" {
  description = "Database port (used if create_database_secret is true)"
  type        = number
  default     = 5432
}

variable "database_name" {
  description = "Database name for shared_data_layer (documents, chunks, knowledge graph)"
  type        = string
  default     = "housing"
}

variable "auth_database_name" {
  description = "Database name for auth-service (users, tokens) - separate from shared_data_layer"
  type        = string
  default     = "auth_db"
}

# =============================================================================
# EC2 Configuration for Microservices
# =============================================================================

variable "ec2_instance_type" {
  description = "EC2 instance type for microservices host"
  type        = string
  default     = "t3.medium"
}

variable "ec2_key_pair_name" {
  description = "Name of the SSH key pair for EC2 access"
  type        = string
  default     = ""
}

variable "ec2_subnet_id" {
  description = "Subnet ID for EC2 instance (defaults to first private subnet)"
  type        = string
  default     = ""
}

variable "ec2_public_ip" {
  description = "Whether to assign a public IP to the EC2 instance"
  type        = bool
  default     = true
}

variable "ec2_volume_size" {
  description = "Root volume size in GB"
  type        = number
  default     = 30
}

variable "create_elastic_ip" {
  description = "Whether to create an Elastic IP for stable addressing"
  type        = bool
  default     = false
}

variable "ssh_allowed_cidrs" {
  description = "CIDR blocks allowed to SSH to EC2"
  type        = list(string)
  default     = ["0.0.0.0/0"] # Restrict in production!
}

variable "vpc_cidr_blocks" {
  description = "VPC CIDR blocks for internal service access"
  type        = list(string)
  default     = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
}

# =============================================================================
# Git Repository Configuration
# =============================================================================

variable "git_repo" {
  description = "Git repository URL to clone on EC2"
  type        = string
  default     = ""
}

variable "git_branch" {
  description = "Git branch to checkout"
  type        = string
  default     = "master"
}

variable "git_token" {
  description = "GitHub Personal Access Token for private repos (stored in Secrets Manager)"
  type        = string
  default     = ""
  sensitive   = true
}
