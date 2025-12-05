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
AUTH_DB="${auth_db}"
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
# 2. CLONE REPOSITORIES
# =============================================================================
echo "[2/8] Cloning repositories..."
mkdir -p $APP_DIR

# Configure git credentials for private repos (if token provided)
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
    
    # Store credentials for ec2-user too (for deploy.sh)
    mkdir -p /home/ec2-user
    cp /root/.git-credentials /home/ec2-user/.git-credentials
    chown ec2-user:ec2-user /home/ec2-user/.git-credentials
    chmod 600 /home/ec2-user/.git-credentials
    sudo -u ec2-user git config --global credential.helper store
    
    echo "  Using token authentication for private repos"
fi

# Clone main backend repository
if [ -n "$GIT_REPO" ]; then
    # Convert SSH URL to HTTPS if needed
    MAIN_REPO="$GIT_REPO"
    if [[ "$MAIN_REPO" == git@* ]]; then
        MAIN_REPO=$(echo "$MAIN_REPO" | sed 's#git@\([^:]*\):#https://\1/#')
    fi
    
    git clone --branch $GIT_BRANCH --depth 1 $MAIN_REPO $WORK_DIR
else
    mkdir -p $WORK_DIR
    aws s3 cp s3://$S3_BUCKET/configs/docker-compose.yml $WORK_DIR/docker-compose.yml
fi

# Clone frontend repository
FRONTEND_REPO="https://github.com/VizonomyBO/housing-frontend"
FRONTEND_DIR="$APP_DIR/frontend"

echo "  Cloning frontend repository..."
if [[ "$FRONTEND_REPO" == git@* ]]; then
    FRONTEND_REPO=$(echo "$FRONTEND_REPO" | sed 's#git@\([^:]*\):#https://\1/#')
fi

git clone --depth 1 $FRONTEND_REPO $FRONTEND_DIR || {
    echo "  Warning: Failed to clone frontend repo, continuing..."
    mkdir -p $FRONTEND_DIR
}

cd $WORK_DIR

# =============================================================================
# 3. CREATE FRONTEND ENVIRONMENT FILE
# =============================================================================
echo "[3/8] Creating frontend environment file..."
if [ -d "$FRONTEND_DIR" ]; then
    # Use relative URLs since frontend and API are served from the same nginx instance
    # This works regardless of IP/domain changes and is more flexible
    AUTH_URL="/api/auth"
    USER_URL="/api/users"
    
    # Create frontend .env file
    cat > $FRONTEND_DIR/.env << EOF
# Frontend Environment Variables
# Public content S3 bucket
VITE_PUBLIC_CONTENT_URL=https://housing-public-content.s3.us-east-1.amazonaws.com

# API endpoints (via nginx proxy - relative URLs work since same domain)
VITE_BASE_AUTH_URL=$AUTH_URL
VITE_BASE_USER_URL=$USER_URL
EOF
    
    chmod 644 $FRONTEND_DIR/.env
    echo "  Created frontend .env file with nginx proxy URLs"
else
    echo "  Frontend directory not found, skipping .env creation"
fi

# =============================================================================
# 4. BUILD FRONTEND (if needed)
# =============================================================================
echo "[4/8] Building frontend..."
if [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
    cd $FRONTEND_DIR
    
    # Install Node.js 20+ if not present (for frontend build - React Router requires Node 20+)
    if ! command -v node &> /dev/null; then
        echo "  Installing Node.js 20..."
        # Install Node.js 20 from NodeSource
        curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
        dnf install -y nodejs
    else
        # Check if Node version is >= 20, upgrade if needed
        NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$NODE_VERSION" -lt 20 ]; then
            echo "  Upgrading Node.js to version 20..."
            curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
            dnf install -y nodejs
        fi
    fi
    
    # Install dependencies and build
    echo "  Installing frontend dependencies..."
    npm install --production=false || npm install
    
    # Build frontend (common build commands)
    if [ -f "$FRONTEND_DIR/package.json" ]; then
        echo "  Building frontend..."
        # Try common build scripts
        npm run build 2>/dev/null || npm run build:prod 2>/dev/null || {
            echo "  Warning: No build script found, assuming pre-built or different structure"
        }
    fi
else
    echo "  Frontend directory not found or no package.json, skipping build"
fi

cd $WORK_DIR

# =============================================================================
# 5. CREATE BACKEND ENVIRONMENT FILE
# =============================================================================
echo "[5/8] Creating backend environment file..."
cat > $WORK_DIR/.env << EOF
# Database Configuration (two databases on same postgres instance)
# - housing: shared_data_layer (documents, chunks, knowledge graph)
# - auth_db: auth-service (users, refresh tokens)
POSTGRES_DB=$POSTGRES_DB
AUTH_DB=$AUTH_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
# JWT
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=15
# Environment
FLASK_ENV=production
NODE_ENV=production
LOG_LEVEL=info
EOF
chmod 600 $WORK_DIR/.env

# =============================================================================
# 6. CONFIGURE NGINX
# =============================================================================
echo "[6/8] Configuring Nginx..."

# Ensure frontend directory has correct permissions for nginx
if [ -d "$FRONTEND_DIR" ]; then
    echo "  Setting frontend directory permissions..."
    chown -R nginx:nginx $FRONTEND_DIR 2>/dev/null || chown -R root:root $FRONTEND_DIR
    chmod -R 755 $FRONTEND_DIR
    
    # Find and set permissions on build directory
    for build_dir in dist build public out; do
        if [ -d "$FRONTEND_DIR/$build_dir" ]; then
            chown -R nginx:nginx "$FRONTEND_DIR/$build_dir" 2>/dev/null || chown -R root:root "$FRONTEND_DIR/$build_dir"
            chmod -R 755 "$FRONTEND_DIR/$build_dir"
            echo "  Found build directory: $build_dir"
        fi
    done
fi

# Replace main nginx.conf (our config is a full config, not a partial)
aws s3 cp s3://$S3_BUCKET/configs/nginx.conf /etc/nginx/conf.d/vizonomy.conf
nginx -t
systemctl enable nginx
systemctl restart nginx

# =============================================================================
# 7. CREATE SYSTEMD SERVICE (auto-restart on reboot)
# =============================================================================
echo "[7/8] Creating systemd service..."
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
# 8. BUILD AND START ALL SERVICES
# =============================================================================
echo "[8/8] Building and starting all services..."
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
cat > $APP_DIR/deploy.sh << 'EOF'
#!/bin/bash
set -e
cd /opt/vizonomy/repo && git pull
cd /opt/vizonomy/frontend && git pull 2>/dev/null || true
cat > /opt/vizonomy/frontend/.env << E
VITE_PUBLIC_CONTENT_URL=https://housing-public-content.s3.us-east-1.amazonaws.com
VITE_BASE_AUTH_URL=/api/auth
VITE_BASE_USER_URL=/api/users
E
[ -f package.json ] && npm install && npm run build 2>/dev/null || true
cd /opt/vizonomy/repo && docker compose build --parallel && docker compose up -d
EOF

cat > $APP_DIR/logs.sh << 'EOF'
#!/bin/bash
cd /opt/vizonomy/repo && docker compose logs -f "$@"
EOF

cat > $APP_DIR/status.sh << 'EOF'
#!/bin/bash
cd /opt/vizonomy/repo && docker compose ps
curl -sf http://localhost:5001/health && echo " ✅ Auth" || echo " ❌ Auth"
curl -sf http://localhost:5002/v1/health && echo " ✅ Users" || echo " ❌ Users"
curl -sf http://localhost:3000/health && echo " ✅ Swagger" || echo " ❌ Swagger"
EOF

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
