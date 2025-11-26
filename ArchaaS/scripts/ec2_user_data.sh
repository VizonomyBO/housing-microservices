#!/bin/bash
set -e

# =============================================================================
# EC2 User Data Script - FULLY AUTOMATIC DEPLOYMENT
# No manual intervention required
# =============================================================================

# Set HOME for git and other tools (user data runs without HOME set)
export HOME=/root

exec > >(tee /var/log/vizonomy-setup.log) 2>&1
echo "========================================="
echo "Starting Vizonomy Setup - $(date)"
echo "========================================="

# Variables from Terraform
POSTGRES_DB="${postgres_db}"
POSTGRES_USER="${postgres_user}"
POSTGRES_PASSWORD="${postgres_password}"
AWS_REGION="${aws_region}"
S3_BUCKET="${s3_bucket}"
GIT_REPO="${git_repo}"
GIT_BRANCH="${git_branch}"
GIT_TOKEN="${git_token}"

APP_DIR="/opt/vizonomy"
WORK_DIR="$APP_DIR/repo"

# =============================================================================
# 1. INSTALL DEPENDENCIES
# =============================================================================
echo "[1/6] Installing dependencies..."
dnf update -y
# Note: curl-minimal is pre-installed on AL2023, don't install full curl (conflicts)
dnf install -y docker git nginx

# Install docker compose plugin (v2 - uses "docker compose" syntax)
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Also create symlink for docker-compose command
ln -sf /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose

# Install buildx plugin for docker build (latest stable)
mkdir -p /root/.docker/cli-plugins
curl -SL "https://github.com/docker/buildx/releases/download/v0.19.2/buildx-v0.19.2.linux-amd64" -o /root/.docker/cli-plugins/docker-buildx
chmod +x /root/.docker/cli-plugins/docker-buildx

systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user

# Verify docker compose
docker compose version

# =============================================================================
# 2. CLONE REPOSITORY
# =============================================================================
echo "[2/6] Cloning repository..."
mkdir -p $APP_DIR

if [ -n "$GIT_REPO" ]; then
    # Configure git credentials for private repos
    if [ -n "$GIT_TOKEN" ]; then
        # Extract host from repo URL and configure credential helper
        GIT_HOST=$(echo "$GIT_REPO" | sed -n 's#.*://\([^/]*\)/.*#\1#p')
        if [ -z "$GIT_HOST" ]; then
            GIT_HOST="github.com"  # Default for ssh-style URLs
        fi
        
        # Store credentials securely
        git config --global credential.helper store
        echo "https://git:$GIT_TOKEN@$GIT_HOST" > /root/.git-credentials
        chmod 600 /root/.git-credentials
        
        # Convert SSH URL to HTTPS if needed
        if [[ "$GIT_REPO" == git@* ]]; then
            GIT_REPO=$(echo "$GIT_REPO" | sed 's#git@\([^:]*\):#https://\1/#')
        fi
        
        echo "  Using token authentication for private repo"
    fi
    
    git clone --branch $GIT_BRANCH --depth 1 $GIT_REPO $WORK_DIR
    
    # Store credentials for ec2-user too (for deploy.sh)
    if [ -n "$GIT_TOKEN" ]; then
        mkdir -p /home/ec2-user
        cp /root/.git-credentials /home/ec2-user/.git-credentials
        chown ec2-user:ec2-user /home/ec2-user/.git-credentials
        chmod 600 /home/ec2-user/.git-credentials
        sudo -u ec2-user git config --global credential.helper store
    fi
else
    mkdir -p $WORK_DIR
    aws s3 cp s3://$S3_BUCKET/configs/docker-compose.yml $WORK_DIR/docker-compose.yml
fi

cd $WORK_DIR

# =============================================================================
# 3. CREATE ENVIRONMENT FILE
# =============================================================================
echo "[3/6] Creating environment file..."
cat > $WORK_DIR/.env << EOF
POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=15
FLASK_ENV=production
NODE_ENV=production
LOG_LEVEL=info
EOF
chmod 600 $WORK_DIR/.env

# =============================================================================
# 4. CONFIGURE NGINX
# =============================================================================
echo "[4/6] Configuring Nginx..."
aws s3 cp s3://$S3_BUCKET/configs/nginx.conf /etc/nginx/conf.d/vizonomy.conf
rm -f /etc/nginx/conf.d/default.conf 2>/dev/null || true
nginx -t
systemctl start nginx
systemctl enable nginx

# =============================================================================
# 5. CREATE SYSTEMD SERVICE (auto-restart on reboot)
# =============================================================================
echo "[5/6] Creating systemd service..."
cat > /etc/systemd/system/vizonomy.service << EOF
[Unit]
Description=Vizonomy Microservices
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$WORK_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vizonomy.service

# =============================================================================
# 6. BUILD AND START ALL SERVICES
# =============================================================================
echo "[6/6] Building and starting all services..."
cd $WORK_DIR

# Build all images (using docker compose v2)
docker compose build --parallel

# Start services
docker compose up -d

# Wait for postgres to be healthy
echo "Waiting for PostgreSQL..."
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U $POSTGRES_USER 2>/dev/null; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 5
done

# Wait for all services
echo "Waiting for services to start..."
sleep 30

# =============================================================================
# HELPER SCRIPTS
# =============================================================================
cat > $APP_DIR/deploy.sh << 'SCRIPT'
#!/bin/bash
set -e
cd /opt/vizonomy/repo
echo "📦 Pulling latest code..."
git pull
echo "🔨 Building images..."
docker compose build --parallel
echo "🚀 Restarting services (database volume preserved)..."
docker compose up -d
echo "✅ Deployment complete! Database data preserved."
SCRIPT

# DANGEROUS: Only use if you really want to wipe the database
cat > $APP_DIR/reset-db.sh << 'SCRIPT'
#!/bin/bash
echo "⚠️  WARNING: This will DELETE ALL DATABASE DATA!"
read -p "Type 'DELETE' to confirm: " confirm
if [ "$confirm" = "DELETE" ]; then
    cd /opt/vizonomy/repo
    docker compose down -v
    docker compose up -d
    echo "Database wiped and recreated."
else
    echo "Cancelled."
fi
SCRIPT

cat > $APP_DIR/logs.sh << 'SCRIPT'
#!/bin/bash
cd /opt/vizonomy/repo && docker compose logs -f "$@"
SCRIPT

cat > $APP_DIR/status.sh << 'SCRIPT'
#!/bin/bash
echo "=== Services ==="
cd /opt/vizonomy/repo && docker compose ps
echo ""
echo "=== Health Checks ==="
curl -sf http://localhost:5001/health && echo " ✅ Auth" || echo " ❌ Auth"
curl -sf http://localhost:5002/v1/health && echo " ✅ Users" || echo " ❌ Users"  
curl -sf http://localhost:3000/health && echo " ✅ Swagger" || echo " ❌ Swagger"
SCRIPT

chmod +x $APP_DIR/*.sh
chown -R ec2-user:ec2-user $APP_DIR

# =============================================================================
# DONE
# =============================================================================
PUBLIC_IP=$(curl -sf http://169.254.169.254/latest/meta-data/public-ipv4 || echo "UNKNOWN")

echo ""
echo "========================================="
echo "✅ DEPLOYMENT COMPLETE - $(date)"
echo "========================================="
echo ""
echo "🌐 http://$PUBLIC_IP"
echo ""
echo "📍 API Endpoints:"
echo "   /api/auth/   → Auth Service"
echo "   /api/users/  → User Service"
echo "   /api/docs/   → Swagger"
echo ""
echo "📋 Helper commands (SSH as ec2-user):"
echo "   /opt/vizonomy/status.sh  → Check health"
echo "   /opt/vizonomy/logs.sh    → View logs"
echo "   /opt/vizonomy/deploy.sh  → Redeploy"
