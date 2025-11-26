#!/bin/bash
set -e

# =============================================================================
# Vizonomy Infrastructure Deployment Script
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICES_DIR="$(dirname "$PROJECT_DIR")/services"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    VIZONOMY INFRASTRUCTURE DEPLOYMENT                        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v terraform &> /dev/null; then
    echo -e "${RED}Error: Terraform is not installed${NC}"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites met${NC}"
echo ""

# Parse arguments
ACTION="${1:-plan}"
ENVIRONMENT="${2:-dev}"

cd "$PROJECT_DIR"

case "$ACTION" in
    init)
        echo -e "${YELLOW}Initializing Terraform...${NC}"
        terraform init
        echo -e "${GREEN}✓ Terraform initialized${NC}"
        ;;

    plan)
        echo -e "${YELLOW}Running Terraform plan...${NC}"
        terraform plan -out=tfplan
        echo -e "${GREEN}✓ Plan complete${NC}"
        ;;

    apply)
        echo -e "${YELLOW}Applying Terraform configuration...${NC}"
        if [ -f tfplan ]; then
            terraform apply tfplan
        else
            terraform apply -auto-approve
        fi
        echo -e "${GREEN}✓ Infrastructure deployed${NC}"
        
        # Get outputs
        EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null || echo "")
        if [ -n "$EC2_IP" ]; then
            echo ""
            echo -e "${GREEN}EC2 Instance is ready at: ${EC2_IP}${NC}"
            echo "Wait a few minutes for the instance to fully initialize"
        fi
        ;;

    destroy)
        echo -e "${RED}WARNING: This will destroy all infrastructure!${NC}"
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" == "yes" ]; then
            terraform destroy -auto-approve
            echo -e "${GREEN}✓ Infrastructure destroyed${NC}"
        else
            echo "Aborted"
        fi
        ;;

    build-images)
        echo -e "${YELLOW}Building Docker images for microservices...${NC}"
        
        # Get AWS account ID and region
        AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        AWS_REGION=$(aws configure get region || echo "us-east-1")
        
        # Create ECR repositories if they don't exist
        for SERVICE in auth-service user-service swagger-service; do
            REPO_NAME="vizonomy-${SERVICE}"
            aws ecr describe-repositories --repository-names "$REPO_NAME" 2>/dev/null || \
                aws ecr create-repository --repository-name "$REPO_NAME"
        done
        
        # Login to ECR
        aws ecr get-login-password --region "$AWS_REGION" | \
            docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
        
        # Build and push images
        for SERVICE in auth-service user-service swagger-service; do
            SERVICE_DIR="$SERVICES_DIR/$SERVICE"
            if [ -d "$SERVICE_DIR" ]; then
                echo -e "${YELLOW}Building ${SERVICE}...${NC}"
                docker build -t "vizonomy-${SERVICE}:latest" "$SERVICE_DIR"
                docker tag "vizonomy-${SERVICE}:latest" \
                    "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/vizonomy-${SERVICE}:latest"
                docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/vizonomy-${SERVICE}:latest"
                echo -e "${GREEN}✓ ${SERVICE} pushed to ECR${NC}"
            fi
        done
        ;;

    run-migration)
        echo -e "${YELLOW}Running database migration on EC2...${NC}"
        
        EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null)
        KEY_NAME=$(terraform output -json deployment_info 2>/dev/null | jq -r '.ec2_key_pair_name // empty')
        
        if [ -z "$EC2_IP" ]; then
            echo -e "${RED}Error: Could not get EC2 IP. Is infrastructure deployed?${NC}"
            exit 1
        fi
        
        # Copy migration file
        scp -o StrictHostKeyChecking=no \
            "$PROJECT_DIR/migrations/001_create_documents_table.sql" \
            "ec2-user@${EC2_IP}:/opt/vizonomy/migrations/"
        
        # Run migration
        ssh -o StrictHostKeyChecking=no "ec2-user@${EC2_IP}" \
            "docker exec -i vizonomy-postgres psql -U vizonomy_user -d vizonomy_db < /opt/vizonomy/migrations/001_create_documents_table.sql"
        
        echo -e "${GREEN}✓ Migration complete${NC}"
        ;;

    status)
        echo -e "${YELLOW}Checking infrastructure status...${NC}"
        terraform output summary
        ;;

    ssh)
        EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null)
        if [ -z "$EC2_IP" ]; then
            echo -e "${RED}Error: Could not get EC2 IP${NC}"
            exit 1
        fi
        echo -e "${YELLOW}Connecting to EC2 instance...${NC}"
        ssh -o StrictHostKeyChecking=no "ec2-user@${EC2_IP}"
        ;;

    *)
        echo "Usage: $0 {init|plan|apply|destroy|build-images|run-migration|status|ssh} [environment]"
        echo ""
        echo "Commands:"
        echo "  init           - Initialize Terraform"
        echo "  plan           - Create execution plan"
        echo "  apply          - Apply infrastructure changes"
        echo "  destroy        - Destroy all infrastructure"
        echo "  build-images   - Build and push Docker images to ECR"
        echo "  run-migration  - Run database migrations on EC2"
        echo "  status         - Show infrastructure status"
        echo "  ssh            - SSH into EC2 instance"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}Done!${NC}"

