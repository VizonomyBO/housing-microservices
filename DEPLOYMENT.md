# Deployment Guide

Complete guide for deploying the Microservices Platform in various environments.

## Table of Contents

1. [Local Development](#local-development)
2. [Docker Compose Production](#docker-compose-production)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Cloud Deployment](#cloud-deployment)
5. [Environment Configuration](#environment-configuration)
6. [Database Setup](#database-setup)
7. [Security Hardening](#security-hardening)
8. [Monitoring & Logging](#monitoring--logging)
9. [Backup & Recovery](#backup--recovery)
10. [Troubleshooting](#troubleshooting)

---

## Local Development

### Prerequisites

- Docker Desktop 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 10GB disk space

### Steps

1. **Clone the repository**
```bash
git clone <repository-url>
cd ia-project
```

2. **Configure environment**
```bash
cp env.example .env
# Edit .env with your settings
```

3. **Start services**
```bash
docker-compose up --build
```

4. **Verify deployment**
```bash
# Check all services are healthy
docker-compose ps

# Test API
./test-api.sh

# Open docs
open http://localhost:3000/docs
```

### Development Mode

**Account Service (Python)**
```bash
cd services/account-service
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL only
docker-compose up postgres -d

# Set environment
export DATABASE_URL=postgresql://account_user:secure_password@localhost:5432/account_db
export JWT_SECRET_KEY=dev-secret-key

# Run locally
python run.py
```

**Swagger Service (TypeScript)**
```bash
cd services/swagger-service
npm install

# Set environment
export PORT=3000
export ACCOUNT_SERVICE_URL=http://localhost:5000

# Run in dev mode
npm run dev
```

---

## Docker Compose Production

### Prerequisites

- Production server with Docker
- Domain name configured
- SSL certificates
- At least 8GB RAM
- 50GB disk space

### Production Configuration

1. **Update environment variables**

Create `.env` file:
```bash
# Database - Use strong passwords!
DATABASE_URL=postgresql://prod_user:$(openssl rand -base64 32)@postgres:5432/prod_db
POSTGRES_DB=prod_db
POSTGRES_USER=prod_user
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# JWT - Generate strong secret
JWT_SECRET_KEY=$(openssl rand -base64 64)
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000

# Application
FLASK_ENV=production
NODE_ENV=production

# Security
CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com

# Email (configure your SMTP)
SMTP_SERVER=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=your-sendgrid-api-key
EMAIL_FROM=noreply@yourdomain.com
```

2. **Update docker-compose.yml for production**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    container_name: account-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - microservices-network
    # Don't expose port in production - use only internal network

  account-service:
    build:
      context: ./services/account-service
      dockerfile: Dockerfile
    container_name: account-service
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_ACCESS_TOKEN_EXPIRES=${JWT_ACCESS_TOKEN_EXPIRES}
      - JWT_REFRESH_TOKEN_EXPIRES=${JWT_REFRESH_TOKEN_EXPIRES}
      - FLASK_ENV=production
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - microservices-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  swagger-service:
    build:
      context: ./services/swagger-service
      dockerfile: Dockerfile
    container_name: swagger-service
    restart: unless-stopped
    depends_on:
      account-service:
        condition: service_healthy
    environment:
      - NODE_ENV=production
      - PORT=3000
      - LOG_LEVEL=info
      - ACCOUNT_SERVICE_URL=http://account-service:5000
    ports:
      - "3000:3000"  # Expose to reverse proxy
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - microservices-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  postgres_data:
    driver: local

networks:
  microservices-network:
    driver: bridge
```

3. **Deploy**

```bash
# Pull latest images
docker-compose pull

# Build and start
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### Nginx Reverse Proxy

Create `/etc/nginx/sites-available/api`:

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name api.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Swagger Service (Documentation)
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Account Service API
    location /auth {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Rate limiting
        limit_req zone=api burst=20 nodelay;
    }

    # Logging
    access_log /var/log/nginx/api_access.log;
    error_log /var/log/nginx/api_error.log;
}

# Rate limiting zone
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
```

Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (GKE, EKS, AKS, or local)
- kubectl configured
- Helm 3+ (optional)

### Namespace

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: microservices-platform
```

### Secrets

```yaml
# secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
  namespace: microservices-platform
type: Opaque
stringData:
  database-url: "postgresql://user:password@postgres:5432/db"
  jwt-secret: "your-jwt-secret-min-32-chars"
  postgres-password: "your-postgres-password"
```

Apply:
```bash
kubectl apply -f namespace.yaml
kubectl apply -f secrets.yaml
```

### PostgreSQL

```yaml
# postgres-deployment.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: microservices-platform
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: microservices-platform
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        env:
        - name: POSTGRES_DB
          value: "account_db"
        - name: POSTGRES_USER
          value: "account_user"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: postgres-password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: microservices-platform
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
  type: ClusterIP
```

### Account Service

```yaml
# account-service-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: account-service
  namespace: microservices-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: account-service
  template:
    metadata:
      labels:
        app: account-service
    spec:
      containers:
      - name: account-service
        image: your-registry/account-service:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: database-url
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: jwt-secret
        - name: FLASK_ENV
          value: "production"
        ports:
        - containerPort: 5000
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
---
apiVersion: v1
kind: Service
metadata:
  name: account-service
  namespace: microservices-platform
spec:
  selector:
    app: account-service
  ports:
  - port: 5000
    targetPort: 5000
  type: ClusterIP
```

### Swagger Service

```yaml
# swagger-service-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: swagger-service
  namespace: microservices-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: swagger-service
  template:
    metadata:
      labels:
        app: swagger-service
    spec:
      containers:
      - name: swagger-service
        image: your-registry/swagger-service:latest
        env:
        - name: NODE_ENV
          value: "production"
        - name: PORT
          value: "3000"
        - name: ACCOUNT_SERVICE_URL
          value: "http://account-service:5000"
        ports:
        - containerPort: 3000
        livenessProbe:
          httpGet:
            path: /health
            port: 3000
          initialDelaySeconds: 15
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: swagger-service
  namespace: microservices-platform
spec:
  selector:
    app: swagger-service
  ports:
  - port: 3000
    targetPort: 3000
  type: LoadBalancer
```

### Deploy to Kubernetes

```bash
# Apply all manifests
kubectl apply -f namespace.yaml
kubectl apply -f secrets.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f account-service-deployment.yaml
kubectl apply -f swagger-service-deployment.yaml

# Check status
kubectl get pods -n microservices-platform
kubectl get services -n microservices-platform

# View logs
kubectl logs -n microservices-platform -l app=account-service
kubectl logs -n microservices-platform -l app=swagger-service
```

---

## Cloud Deployment

### AWS (ECS/Fargate)

1. Build and push Docker images to ECR
2. Create ECS cluster
3. Create task definitions
4. Create services
5. Configure ALB
6. Set up RDS PostgreSQL

### Google Cloud (GKE)

1. Create GKE cluster
2. Push images to GCR
3. Deploy with kubectl or Helm
4. Set up Cloud SQL
5. Configure Ingress

### Azure (AKS)

1. Create AKS cluster
2. Push images to ACR
3. Deploy with kubectl
4. Set up Azure Database for PostgreSQL
5. Configure Application Gateway

---

## Environment Configuration

### Required Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/db
POSTGRES_DB=account_db
POSTGRES_USER=account_user
POSTGRES_PASSWORD=<strong-password>

# JWT
JWT_SECRET_KEY=<min-32-chars>
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000

# Application
FLASK_ENV=production
NODE_ENV=production
PORT=3000

# Services
ACCOUNT_SERVICE_URL=http://account-service:5000

# Security
CORS_ORIGINS=https://yourdomain.com
RATE_LIMIT_PER_MINUTE=60

# Email (optional)
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=user
SMTP_PASSWORD=pass
EMAIL_FROM=noreply@yourdomain.com
```

---

## Database Setup

### PostgreSQL Production Setup

```sql
-- Create database
CREATE DATABASE account_db;

-- Create user
CREATE USER account_user WITH ENCRYPTED PASSWORD 'strong_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE account_db TO account_user;

-- Connect to database
\c account_db

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO account_user;
```

### Backups

**Automated backups (cron)**:
```bash
#!/bin/bash
# backup.sh
BACKUP_DIR=/backups
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T postgres pg_dump -U account_user account_db | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

Add to crontab:
```bash
0 2 * * * /path/to/backup.sh
```

### Restore

```bash
gunzip < backup.sql.gz | docker-compose exec -T postgres psql -U account_user account_db
```

---

## Security Hardening

### Production Checklist

- [ ] Use strong, unique passwords (32+ characters)
- [ ] Use secrets management (AWS Secrets Manager, Vault)
- [ ] Enable SSL/TLS everywhere
- [ ] Configure firewall rules
- [ ] Disable unnecessary ports
- [ ] Use non-root users in containers
- [ ] Scan images for vulnerabilities
- [ ] Enable audit logging
- [ ] Set up intrusion detection
- [ ] Regular security updates
- [ ] Implement rate limiting
- [ ] Use HTTPS only
- [ ] Configure CORS properly
- [ ] Enable security headers
- [ ] Implement monitoring
- [ ] Set up alerts

---

## Monitoring & Logging

### Prometheus + Grafana

See separate monitoring setup guide.

### ELK Stack

See separate logging setup guide.

### Cloud Monitoring

- AWS CloudWatch
- Google Cloud Monitoring
- Azure Monitor

---

## Troubleshooting

### Common Issues

**Services not starting**
```bash
# Check logs
docker-compose logs

# Check individual service
docker-compose logs account-service

# Restart services
docker-compose restart
```

**Database connection failed**
```bash
# Check PostgreSQL
docker-compose exec postgres psql -U account_user -d account_db

# Check connectivity
docker-compose exec account-service nc -zv postgres 5432
```

**Port conflicts**
```bash
# Find process using port
lsof -i :3000
lsof -i :5000

# Kill process
kill -9 <PID>
```

---

For more details, see the main [README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

