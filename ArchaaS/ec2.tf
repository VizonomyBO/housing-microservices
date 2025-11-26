# EC2 Instance for Microservices and PostgreSQL Database
# Cost-effective solution for development and testing

# Get latest Amazon Linux 2023 AMI
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# EC2 Instance
resource "aws_instance" "microservices" {
  ami                         = data.aws_ami.amazon_linux_2023.id
  instance_type               = var.ec2_instance_type
  key_name                    = var.ec2_key_pair_name
  vpc_security_group_ids      = [aws_security_group.ec2_microservices.id]
  subnet_id                   = var.ec2_subnet_id != "" ? var.ec2_subnet_id : (length(var.private_subnet_ids) > 0 ? var.private_subnet_ids[0] : null)
  associate_public_ip_address = var.ec2_public_ip
  iam_instance_profile        = aws_iam_instance_profile.ec2_microservices.name

  root_block_device {
    volume_size           = var.ec2_volume_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  user_data = base64encode(templatefile("${path.module}/scripts/ec2_user_data.sh", {
    postgres_db       = var.database_name
    postgres_user     = var.database_username
    postgres_password = var.database_password
    project_name      = var.project_name
    environment       = var.environment
    aws_region        = var.aws_region
    s3_bucket         = aws_s3_bucket.raw_documents.id
    git_repo          = var.git_repo
    git_branch        = var.git_branch
    git_token         = var.git_token
  }))

  depends_on = [
    aws_s3_object.nginx_config,
    aws_s3_object.docker_compose
  ]

  tags = {
    Name        = "${var.project_name}-microservices-${var.environment}"
    Environment = var.environment
    Purpose     = "Microservices and PostgreSQL host"
  }

  # IMPORTANT: Prevent EC2 replacement to preserve database data
  # Changes to user_data won't trigger recreation
  # To apply user_data changes, SSH in and run /opt/vizonomy/deploy.sh
  lifecycle {
    ignore_changes = [
      user_data,
      ami  # Also ignore AMI updates to preserve data
    ]
    create_before_destroy = true
  }
}

# Security Group for EC2 Instance
resource "aws_security_group" "ec2_microservices" {
  name        = "${var.project_name}-ec2-microservices-${var.environment}"
  description = "Security group for microservices EC2 instance"
  vpc_id      = var.vpc_id

  # SSH access (restrict to your IP in production)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_allowed_cidrs
    description = "SSH access"
  }

  # HTTP (Nginx reverse proxy)
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP - Nginx reverse proxy"
  }

  # HTTPS (for future SSL)
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS"
  }

  # PostgreSQL from Lambda
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "PostgreSQL access from Lambda"
  }

  # PostgreSQL from VPC (for other services)
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.vpc_cidr_blocks
    description = "PostgreSQL access from VPC"
  }

  # Auth Service
  ingress {
    from_port   = 5001
    to_port     = 5001
    protocol    = "tcp"
    cidr_blocks = var.vpc_cidr_blocks
    description = "Auth service"
  }

  # User Service
  ingress {
    from_port   = 5002
    to_port     = 5002
    protocol    = "tcp"
    cidr_blocks = var.vpc_cidr_blocks
    description = "User service"
  }

  # Swagger Service
  ingress {
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = var.vpc_cidr_blocks
    description = "Swagger service"
  }

  # HTTP/HTTPS for package updates
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name        = "${var.project_name}-ec2-microservices-sg"
    Environment = var.environment
  }
}

# IAM Role for EC2
resource "aws_iam_role" "ec2_microservices" {
  name = "${var.project_name}-ec2-microservices-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-ec2-microservices-role"
    Environment = var.environment
  }
}

# EC2 Instance Profile
resource "aws_iam_instance_profile" "ec2_microservices" {
  name = "${var.project_name}-ec2-microservices-${var.environment}"
  role = aws_iam_role.ec2_microservices.name
}

# Policy for ECR access (to pull Docker images)
resource "aws_iam_role_policy_attachment" "ec2_ecr" {
  role       = aws_iam_role.ec2_microservices.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Policy for CloudWatch Logs
resource "aws_iam_role_policy_attachment" "ec2_cloudwatch" {
  role       = aws_iam_role.ec2_microservices.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Policy for SSM (for Session Manager access - no SSH key needed)
resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2_microservices.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# S3 policy for accessing deployment artifacts
resource "aws_iam_policy" "ec2_s3_access" {
  name        = "${var.project_name}-ec2-s3-access-${var.environment}"
  description = "S3 access for EC2 deployment artifacts"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3Access"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.raw_documents.arn,
          "${aws_s3_bucket.raw_documents.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_s3" {
  role       = aws_iam_role.ec2_microservices.name
  policy_arn = aws_iam_policy.ec2_s3_access.arn
}

# Elastic IP for stable addressing (optional)
resource "aws_eip" "microservices" {
  count    = var.ec2_public_ip && var.create_elastic_ip ? 1 : 0
  instance = aws_instance.microservices.id
  domain   = "vpc"

  tags = {
    Name        = "${var.project_name}-microservices-eip"
    Environment = var.environment
  }
}

# CloudWatch Log Group for EC2 logs
resource "aws_cloudwatch_log_group" "ec2_microservices" {
  name              = "/ec2/${var.project_name}-microservices-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-ec2-logs"
    Environment = var.environment
  }
}

# Outputs
output "ec2_instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.microservices.id
}

output "ec2_private_ip" {
  description = "EC2 private IP address"
  value       = aws_instance.microservices.private_ip
}

output "ec2_public_ip" {
  description = "EC2 public IP address"
  value       = var.create_elastic_ip && var.ec2_public_ip ? aws_eip.microservices[0].public_ip : aws_instance.microservices.public_ip
}

output "database_host" {
  description = "Database host (EC2 private IP)"
  value       = aws_instance.microservices.private_ip
}

output "database_connection_string" {
  description = "PostgreSQL connection string for services"
  value       = "postgresql://${var.database_username}:${var.database_password}@${aws_instance.microservices.private_ip}:5432/${var.database_name}"
  sensitive   = true
}

