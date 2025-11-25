# Infrastructure & Deployment

## Overview
This document defines the infrastructure architecture and deployment strategy for the Housing Service. We use **Terraform** for Infrastructure as Code (IaC) and **GitHub Actions** for CI/CD, deploying to a hybrid **ECS Fargate + Lambda** environment on AWS.

## 1. Infrastructure as Code (IaC)
- **Tool**: Terraform (v1.9+ required for latest AWS provider features).
- **State Management**: S3 Backend with DynamoDB locking.
- **Modules**:
    - `vpc`: Networking (Subnets, NAT, IGW).
    - `ec2-asg`: Auto Scaling Groups for application workloads.
    - `postgres-ec2`: Self-managed Postgres on EC2 (cost-optimized vs RDS).
    - `elasticache-serverless`: Valkey (Redis-compatible) serverless cache.
    - `lambda`: Serverless functions for event triggers.
    - `iam`: Least-privilege roles for services.

## 2. Network Layout (VPC)
- **Region**: `us-east-1` (or specific target region).
- **Subnets**:
    - **Public**: ALB (Application Load Balancer), NAT Gateways.
    - **Private App**: EC2 instances (FastAPI, Workers), Lambda functions.
    - **Private Data**: Postgres EC2, ElastiCache Serverless (isolated).
- **Security Groups**:
    - `lb-sg`: Allow 443 from 0.0.0.0/0.
    - `app-sg`: Allow traffic from `lb-sg`.
    - `data-sg`: Allow traffic from `app-sg`.

## 3. Compute Architecture

### 3.1 API Service (FastAPI)
- **Platform**: AWS EC2 with Auto Scaling Group (cost-optimized vs ECS Fargate).
- **Instance Type**: `t3.medium` or `t3a.medium` (2 vCPU, 4 GB RAM) - adjustable based on load testing.
- **Container**: Docker image containing FastAPI + LangGraph runtime, deployed via systemd service.
- **Load Balancer**: Application Load Balancer (ALB) distributing traffic across EC2 instances.

#### Autoscaling Policy
- **Type**: Target Tracking
- **Metrics**:
    - **CPU Target**: 70% average utilization
    - **Memory Target**: 75% average utilization
    - **ALB RequestCountPerTarget**: 1000 requests/target (optional, for HTTP-based scaling)
- **Capacity**:
    - **Min Instances**: 2 (High Availability across AZs)
    - **Max Instances**: 20
- **Cooldown**:
    - **Scale-in Cooldown**: 300s (prevent thrashing)
    - **Scale-out Cooldown**: 60s (fast response to load spikes)

### 3.2 Async Workers
- **Platform**: AWS EC2 (same ASG as API or separate, depending on workload isolation needs).
- **Trigger**: Polling SQS queues (Ingestion, Export).
- **Scaling**: ASG scaling based on SQS Queue Depth (via CloudWatch Alarms).

### 3.3 Database (Postgres)
- **Platform**: Self-managed PostgreSQL on EC2 (cost-optimized vs RDS).
- **Instance Type**: `t3.large` or `r6i.large` (memory-optimized for database workloads).
- **Storage**: EBS gp3 volumes with automated snapshots.
- **High Availability**: Primary-Standby replication (manual setup or using tools like Patroni/repmgr).
- **Backups**: Automated EBS snapshots + pg_dump to S3 (daily).
- **Rationale**: RDS costs 50-100% more than EC2; self-managed Postgres reduces costs with acceptable operational overhead.

### 3.4 Cache (Valkey)
- **Platform**: AWS ElastiCache Serverless for Valkey.
- **Pricing**: Starting at $6/month (33% cheaper than Redis).
- **Scaling**: Automatic scaling based on workload.
- **Rationale**: Serverless eliminates capacity planning; Valkey is Redis-compatible with lower costs.

### 3.5 Event Triggers
- **Platform**: AWS Lambda.
- **Use Case**: S3 Event Notifications (e.g., new file uploaded → trigger ingestion workflow start).
- **Runtime**: Python 3.11+.

## 4. CI/CD Pipeline
- **Platform**: GitHub Actions.

### 4.1 Continuous Integration (CI)
- **Trigger**: Pull Request.
- **Steps**:
    1. **Lint**: `ruff`, `black`.
    2. **Test**: `pytest` (Unit & Contract tests).
    3. **Build**: `docker build`.
    4. **Scan**: Container vulnerability scan (Trivy).

### 4.2 Continuous Deployment (CD)
- **Trigger**: Merge to `main` (Staging) or Release Tag (Production).
- **Steps**:
    1. **Push**: Upload Docker image to AWS ECR with commit SHA tag.
    2. **IaC Apply**: `terraform apply` (updates infra if needed).
    3. **Deploy**: 
        - Pull new Docker image on EC2 instances.
        - Rolling restart via systemd or deployment script (blue-green if configured).
    4. **Verify**: Check `/health/live` endpoint.
    5. **Migrate**: Run DB migrations (via ephemeral EC2 task or SSH to primary DB instance).

## 5. Secrets Management
- **Storage**: AWS Secrets Manager.
- **Injection Method**: 
    - **EC2 Instances**: Secrets fetched at startup via AWS SDK and injected as environment variables into systemd service.
    - **Lambda**: Environment variables fetched at runtime via AWS SDK.
- **IAM Permission**: EC2 instance role and Lambda execution role require `secretsmanager:GetSecretValue` for specified secret ARNs.
- **Policy**: No secrets in Git or Docker images.

**Example (EC2 user-data script)**:
```bash
#!/bin/bash
# Fetch secrets from AWS Secrets Manager
DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id housing/db-password --query SecretString --output text)

# Export as environment variable for systemd service
echo "DB_PASSWORD=$DB_PASSWORD" >> /etc/housing-service/env
systemctl restart housing-service
```
