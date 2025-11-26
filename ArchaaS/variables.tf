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
  description = "VPC ID for Lambda deployment"
  type        = string
  default     = ""
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for Lambda VPC configuration"
  type        = list(string)
  default     = []
}

# S3 Configuration
variable "allowed_origins" {
  description = "Allowed origins for CORS (S3 and API Gateway)"
  type        = list(string)
  default     = ["https://*.vizonomy.com", "http://localhost:3000"]
}

# Lambda Configuration
variable "log_level" {
  description = "Lambda log level"
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "presigned_url_expiry_sec" {
  description = "Presigned URL expiration time in seconds"
  type        = number
  default     = 900
}

variable "max_file_size_bytes" {
  description = "Maximum file size for uploads in bytes (default: 100MB)"
  type        = number
  default     = 104857600
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
  description = "Database name (shared database for all services)"
  type        = string
  default     = "housing"
}

# API Gateway Configuration
variable "api_throttle_burst_limit" {
  description = "API Gateway throttling burst limit"
  type        = number
  default     = 100
}

variable "api_throttle_rate_limit" {
  description = "API Gateway throttling rate limit (requests per second)"
  type        = number
  default     = 50
}

# JWT Authorization Configuration
variable "jwt_audience" {
  description = "JWT audience for API Gateway authorizer"
  type        = list(string)
  default     = []
}

variable "jwt_issuer" {
  description = "JWT issuer URL for API Gateway authorizer"
  type        = string
  default     = ""
}

# Custom Domain Configuration
variable "custom_domain_name" {
  description = "Custom domain name for API Gateway (optional)"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate ARN for custom domain (required if custom_domain_name is set)"
  type        = string
  default     = ""
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
