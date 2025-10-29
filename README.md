# Microservices Platform with TypeScript Swagger Aggregator

A comprehensive microservices ecosystem featuring a Flask-based Account Management Service and a TypeScript-based Swagger UI aggregator for centralized API documentation.

## 🚀 Features

### Account Management Service (Flask/Python)
- **Secure Authentication**: JWT-based access and refresh tokens
- **Password Security**: Argon2 hashing algorithm
- **User Management**: Registration, login, password reset
- **Token Rotation**: Secure refresh token management
- **Rate Limiting**: Protection against brute force attacks
- **Input Validation**: Comprehensive security validation
- **OpenAPI Documentation**: Auto-generated API specification

### TypeScript Swagger Aggregator Service
- **Centralized Documentation**: Single portal for all microservices
- **Type-Safe**: Full TypeScript implementation
- **Service Discovery**: Automatic detection and aggregation
- **Health Monitoring**: Real-time service health tracking
- **Interactive UI**: Swagger UI with all services
- **Auto-Refresh**: Periodic spec updates

### Infrastructure
- **Docker Orchestration**: Multi-container deployment
- **PostgreSQL**: Robust data persistence
- **Network Isolation**: Secure inter-service communication
- **Health Checks**: Automated monitoring and recovery

## 📋 Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- (Optional for local dev) Node.js 18+ and Python 3.11+

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Docker Environment                     │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Swagger Aggregator (Port 3000)           │  │
│  │         TypeScript/Node.js/Express               │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │        Account Service (Port 5000)               │  │
│  │        Flask/Python/SQLAlchemy                   │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │        PostgreSQL Database (Port 5432)           │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 🚦 Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd ia-project
cp .env.example .env
```

### 2. Configure Environment Variables

Edit the `.env` file with your configuration:

```bash
# Database
POSTGRES_PASSWORD=your-secure-password

# JWT Secret (must be at least 32 characters)
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production

# Service URLs
ACCOUNT_SERVICE_URL=http://account-service:5000
```

### 3. Start All Services

```bash
docker-compose up --build
```

This will start:
- PostgreSQL database on port 5432
- Account Service on port 5000
- Swagger Aggregator on port 3000

### 4. Access the Services

- **📚 API Documentation**: http://localhost:3000/docs
- **🏠 Landing Page**: http://localhost:3000
- **💚 Health Check**: http://localhost:3000/health
- **📊 System Status**: http://localhost:3000/api/status
- **🔐 Account API**: http://localhost:5000

## 📖 API Documentation

### Account Service Endpoints

#### Authentication
- `POST /auth/register` - Register a new user
- `POST /auth/login` - Login and receive JWT tokens
- `POST /auth/refresh` - Refresh access token
- `POST /auth/logout` - Logout and revoke refresh token
- `POST /auth/forgot-password` - Request password reset
- `POST /auth/reset-password` - Reset password with token
- `POST /auth/verify-token` - Verify access token validity

#### System
- `GET /health` - Service health check
- `GET /status` - Service status information
- `GET /openapi.json` - OpenAPI specification

### Swagger Aggregator Endpoints

#### Documentation
- `GET /` - Landing page
- `GET /docs` - Interactive Swagger UI

#### Health & Monitoring
- `GET /health` - Aggregator health check
- `GET /health/metrics` - Detailed metrics for all services
- `GET /health/metrics/:service` - Metrics for specific service

#### Service Management
- `GET /api/services` - List all registered services
- `GET /api/services/:name` - Get specific service details
- `GET /api/specs` - Aggregated OpenAPI specification
- `GET /api/specs/:service` - Specification for specific service
- `POST /api/refresh` - Force refresh all services
- `POST /api/refresh/:service` - Refresh specific service
- `GET /api/status` - Comprehensive system status

## 🔒 Security Features

### Account Service
- **Argon2 Password Hashing**: Industry-leading password security
- **JWT Tokens**: Stateless authentication with access/refresh pattern
- **Token Rotation**: Automatic refresh token rotation for enhanced security
- **Rate Limiting**: Brute force protection on sensitive endpoints
- **Input Validation**: Comprehensive request validation and sanitization
- **CORS Configuration**: Secure cross-origin resource sharing
- **Security Headers**: HSTS, CSP, X-Frame-Options, etc.
- **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries

### Infrastructure
- **Docker Network Isolation**: Services communicate through private network
- **Non-root Containers**: Enhanced container security
- **Environment Variables**: Secure configuration management
- **Health Checks**: Automated monitoring and recovery

## 🧪 Testing the API

### Register a New User

```bash
curl -X POST http://localhost:5000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "testuser",
    "password": "SecurePass123!",
    "first_name": "Test",
    "last_name": "User"
  }'
```

### Login

```bash
curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "login": "user@example.com",
    "password": "SecurePass123!"
  }'
```

### Refresh Token

```bash
curl -X POST http://localhost:5000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "your-refresh-token"
  }'
```

### Check System Status

```bash
curl http://localhost:3000/api/status
```

## 🛠️ Development

### Local Development - Account Service

```bash
cd services/account-service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://account_user:secure_password@localhost:5432/account_db
export JWT_SECRET_KEY=your-secret-key

# Run the service
python run.py
```

### Local Development - Swagger Service

```bash
cd services/swagger-service

# Install dependencies
npm install

# Set environment variables
export PORT=3000
export ACCOUNT_SERVICE_URL=http://localhost:5000

# Run in development mode (with hot reload)
npm run dev

# Build for production
npm run build
npm start
```

## 📁 Project Structure

```
ia-project/
├── services/
│   ├── account-service/          # Flask authentication service
│   │   ├── app/
│   │   │   ├── __init__.py       # Application factory
│   │   │   ├── config.py         # Configuration
│   │   │   ├── models/           # Database models
│   │   │   ├── services/         # Business logic
│   │   │   ├── api/              # API endpoints
│   │   │   └── utils/            # Utilities
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── run.py
│   │
│   └── swagger-service/          # TypeScript aggregator
│       ├── src/
│       │   ├── app.ts            # Main application
│       │   ├── config/           # Configuration
│       │   ├── types/            # TypeScript types
│       │   ├── services/         # Core services
│       │   ├── routes/           # Route handlers
│       │   ├── middleware/       # Middleware
│       │   └── utils/            # Utilities
│       ├── package.json
│       ├── tsconfig.json
│       └── Dockerfile
│
├── docker-compose.yml            # Docker orchestration
├── .env.example                  # Environment template
├── .gitignore
└── README.md
```

## 🔄 Adding New Microservices

To add a new microservice to the ecosystem:

1. **Create the service** with an OpenAPI endpoint (e.g., `/openapi.json`)
2. **Add health check** endpoint (e.g., `/health`)
3. **Update service registry** in `services/swagger-service/src/config/services.ts`:

```typescript
{
  name: 'Your Service',
  url: 'http://your-service:port',
  specEndpoint: '/openapi.json',
  healthEndpoint: '/health',
  description: 'Service description',
  version: '1.0.0',
  tags: ['tag1', 'tag2'],
  enabled: true,
}
```

4. **Add to docker-compose.yml** if needed
5. **Restart** the Swagger aggregator service

The new service will automatically appear in the unified documentation!

## 🐳 Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f account-service
docker-compose logs -f swagger-service

# Stop all services
docker-compose down

# Stop and remove volumes (database data)
docker-compose down -v

# Rebuild services
docker-compose up --build

# Check service status
docker-compose ps
```

## 🔍 Monitoring

### Check Service Health

```bash
# Overall health
curl http://localhost:3000/health

# Service metrics
curl http://localhost:3000/health/metrics

# Specific service metrics
curl http://localhost:3000/health/metrics/Account%20Service
```

### View Logs

```bash
# All services
docker-compose logs -f

# Account service only
docker-compose logs -f account-service

# Swagger service only
docker-compose logs -f swagger-service

# Database only
docker-compose logs -f postgres
```

## 🐛 Troubleshooting

### Services Not Starting

1. Check if ports are already in use:
```bash
lsof -i :3000
lsof -i :5000
lsof -i :5432
```

2. Check Docker logs:
```bash
docker-compose logs
```

3. Verify environment variables:
```bash
docker-compose config
```

### Database Connection Issues

1. Check PostgreSQL is running:
```bash
docker-compose ps postgres
```

2. Check database logs:
```bash
docker-compose logs postgres
```

3. Verify database connection:
```bash
docker-compose exec postgres psql -U account_user -d account_db
```

### Swagger UI Not Showing Services

1. Check if Account Service is healthy:
```bash
curl http://localhost:5000/health
```

2. Verify OpenAPI spec is accessible:
```bash
curl http://localhost:5000/openapi.json
```

3. Force refresh:
```bash
curl -X POST http://localhost:3000/api/refresh
```

## 📝 Environment Variables

### Account Service
- `DATABASE_URL`: PostgreSQL connection string
- `JWT_SECRET_KEY`: Secret key for JWT signing (min 32 chars)
- `JWT_ACCESS_TOKEN_EXPIRES`: Access token lifetime (seconds)
- `JWT_REFRESH_TOKEN_EXPIRES`: Refresh token lifetime (seconds)

### Swagger Service
- `PORT`: Server port (default: 3000)
- `NODE_ENV`: Environment (development/production)
- `LOG_LEVEL`: Logging level (error/warn/info/debug)
- `ACCOUNT_SERVICE_URL`: Account service URL
- `SPEC_REFRESH_INTERVAL`: Spec refresh interval (ms)
- `HEALTH_CHECK_INTERVAL`: Health check interval (ms)

## 🚀 Production Deployment

For production deployment:

1. **Update environment variables** with production values
2. **Use strong secrets** for JWT and database passwords
3. **Enable HTTPS** with reverse proxy (nginx/traefik)
4. **Set up monitoring** (Prometheus, Grafana)
5. **Configure backups** for PostgreSQL
6. **Set resource limits** in docker-compose.yml
7. **Enable logging** to external service
8. **Use Docker secrets** instead of environment variables

## 📄 License

MIT

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📧 Support

For issues and questions, please open an issue on GitHub.

---

**Built with ❤️ using Flask, TypeScript, Docker, and PostgreSQL**

