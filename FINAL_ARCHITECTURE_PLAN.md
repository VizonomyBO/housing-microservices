# Multi-Microservice Architecture with TypeScript Swagger Aggregator

## Overview

This document outlines the comprehensive architecture for a microservices ecosystem with:
1. **Account Management Microservice** - Flask-based authentication service
2. **TypeScript API Documentation Microservice** - Centralized Swagger UI service aggregating all microservices
3. **PostgreSQL Database** - Data persistence for account service
4. **Docker Orchestration** - Multi-container environment

## System Architecture

```mermaid
graph TB
    subgraph "Docker Environment"
        subgraph "API Gateway Layer"
            SW[Swagger Aggregator Service<br/>TypeScript/Node.js - Port 3000] --> |Discovers| AS
            SW --> |Future Services| FS[Future Microservices]
        end
        
        subgraph "Business Services"
            AS[Account Service<br/>Flask/Python - Port 5000]
            FS[Other Microservices<br/>TBD]
        end
        
        subgraph "Data Layer"
            DB[PostgreSQL<br/>Port 5432]
        end
        
        AS --> DB
        CLIENT[Client Applications] --> SW
        CLIENT --> AS
        DEV[Developers] --> SW
    end
```

## Service Breakdown

### 1. Account Management Microservice
- **Technology**: Flask + SQLAlchemy + Python 3.11
- **Port**: 5000
- **Purpose**: User authentication, registration, password management
- **Database**: PostgreSQL
- **API Documentation**: Exposes OpenAPI spec at `/openapi.json`

### 2. TypeScript API Documentation Microservice (Swagger Aggregator)
- **Technology**: TypeScript + Node.js + Express
- **Port**: 3000
- **Purpose**: Centralized API documentation portal
- **Features**: 
  - Service discovery with type safety
  - Multi-spec aggregation
  - Interactive Swagger UI
  - Health monitoring of services
  - Real-time service status dashboard

### 3. PostgreSQL Database
- **Port**: 5432
- **Purpose**: Data persistence for account service
- **Features**: User data, refresh tokens, audit logs

## TypeScript Swagger Service Architecture

```mermaid
graph LR
    subgraph "TypeScript Swagger Aggregator"
        SD[Service Discovery<br/>TypeScript] --> SA[Spec Aggregator<br/>TypeScript]
        SA --> UI[Swagger UI<br/>Express]
        CF[Config File<br/>JSON/YAML] --> SD
        HM[Health Monitor<br/>TypeScript] --> SD
    end
    
    AS[Account Service<br/>/openapi.json] --> SA
    MS[Future Microservices<br/>/openapi.json] --> SA
    
    UI --> CLIENT[Developers & Clients]
    HM --> DASH[Service Dashboard]
```

## Project Structure

```
microservices-platform/
├── services/
│   ├── account-service/
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── user.py
│   │   │   │   └── refresh_token.py
│   │   │   ├── services/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth_service.py
│   │   │   │   └── user_service.py
│   │   │   ├── api/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py
│   │   │   │   └── system.py
│   │   │   └── utils/
│   │   │       ├── __init__.py
│   │   │       ├── security.py
│   │   │       └── validators.py
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── run.py
│   │
│   └── swagger-service/
│       ├── src/
│       │   ├── app.ts
│       │   ├── config/
│       │   │   ├── services.ts
│       │   │   └── environment.ts
│       │   ├── types/
│       │   │   ├── service.types.ts
│       │   │   ├── openapi.types.ts
│       │   │   └── health.types.ts
│       │   ├── services/
│       │   │   ├── ServiceDiscovery.ts
│       │   │   ├── SpecAggregator.ts
│       │   │   └── HealthMonitor.ts
│       │   ├── routes/
│       │   │   ├── docs.routes.ts
│       │   │   ├── health.routes.ts
│       │   │   └── api.routes.ts
│       │   ├── middleware/
│       │   │   ├── cors.middleware.ts
│       │   │   ├── logging.middleware.ts
│       │   │   └── error.middleware.ts
│       │   └── utils/
│       │       ├── logger.ts
│       │       └── helpers.ts
│       ├── public/
│       │   └── swagger-ui/
│       ├── package.json
│       ├── tsconfig.json
│       ├── Dockerfile
│       └── .dockerignore
│
├── docker-compose.yml
├── .env.example
└── README.md
```

## Key TypeScript Implementation Features

### Type-Safe Service Configuration
```typescript
interface ServiceConfig {
  name: string;
  url: string;
  specEndpoint: string;
  healthEndpoint: string;
  description: string;
  version?: string;
  tags?: string[];
}
```

### Automated Service Discovery
```typescript
class ServiceDiscovery {
  async discoverServices(): Promise<ServiceHealth[]>
  async fetchServiceSpec(service: ServiceConfig): Promise<OpenAPISpec | null>
  getHealthyServices(): ServiceConfig[]
}
```

### Smart Spec Aggregation
```typescript
class SpecAggregator {
  async getAggregatedSpec(): Promise<AggregatedSpec>
  private mergeSpecs(serviceSpecs: Array<{service: ServiceConfig, spec: OpenAPISpec}>): AggregatedSpec
  clearCache(): void
}
```

## Docker Configuration

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: account_db
      POSTGRES_USER: account_user
      POSTGRES_PASSWORD: secure_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U account_user"]
      interval: 30s
      timeout: 10s
      retries: 3

  account-service:
    build: ./services/account-service
    ports:
      - "5000:5000"
    depends_on:
      - postgres
    environment:
      - DATABASE_URL=postgresql://account_user:secure_password@postgres:5432/account_db
      - JWT_SECRET_KEY=your-super-secret-jwt-key
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  swagger-service:
    build: ./services/swagger-service
    ports:
      - "3000:3000"
    depends_on:
      - account-service
    environment:
      - NODE_ENV=production
      - PORT=3000
      - LOG_LEVEL=info
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:
```

## API Endpoints Summary

### Account Management Service (Port 5000)
- `POST /auth/register` - User registration with validation
- `POST /auth/login` - JWT-based authentication
- `POST /auth/refresh` - Token refresh with rotation
- `POST /auth/forgot-password` - Secure password reset initiation
- `POST /auth/reset-password` - Password reset completion
- `POST /auth/logout` - Token revocation
- `GET /health` - Service health check
- `GET /openapi.json` - OpenAPI specification
- `GET /status` - Service status information

### TypeScript Swagger Aggregator Service (Port 3000)
- `GET /` - Interactive Swagger UI with all services
- `GET /docs` - Documentation landing page
- `GET /api/services` - Service registry with health status
- `GET /api/specs` - Aggregated OpenAPI specification
- `GET /api/specs/:service` - Individual service specification
- `GET /health` - Aggregator health check
- `POST /api/refresh` - Force refresh of service specifications
- `GET /api/status` - Comprehensive service status dashboard

## Security Features

### Account Service Security
- **Argon2 Password Hashing**: State-of-the-art password security
- **JWT Access/Refresh Tokens**: Stateless authentication with rotation
- **Rate Limiting**: Brute force protection on authentication endpoints
- **Input Validation**: Comprehensive request validation and sanitization
- **CORS Configuration**: Secure cross-origin resource sharing
- **Security Headers**: HSTS, CSP, X-Frame-Options, etc.
- **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries

### Infrastructure Security
- **Docker Network Isolation**: Services communicate through private network
- **Non-root Container Execution**: Enhanced container security
- **Environment Variable Management**: Secure configuration handling
- **Health Checks**: Automated monitoring and recovery
- **Logging and Monitoring**: Comprehensive audit trails

## Development Workflow

### Getting Started
```bash
# Clone and setup
git clone <repository>
cd microservices-platform

# Start all services
docker-compose up --build

# Access points:
# - Account API: http://localhost:5000
# - Swagger UI: http://localhost:3000
# - PostgreSQL: localhost:5432
```

### TypeScript Development
```bash
cd services/swagger-service

# Install dependencies
npm install

# Development with hot reload
npm run dev

# Build for production
npm run build

# Run tests
npm test
```

## Benefits of This Architecture

1. **Centralized Documentation**: Single source of truth for all API documentation
2. **Type Safety**: TypeScript ensures compile-time error detection
3. **Service Independence**: Each service maintains its own specification
4. **Scalability**: Easy to add new microservices
5. **Developer Experience**: Interactive documentation with real-time updates
6. **Maintainability**: Clear separation of concerns
7. **Monitoring**: Built-in health monitoring and status reporting
8. **Security**: Enterprise-grade security practices

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Set up project structure for multi-microservice architecture
- [ ] Create Docker configuration for all services (docker-compose with multiple containers)
- [ ] Set up PostgreSQL database connection and SQLAlchemy models for account service

### Phase 2: Account Service Implementation
- [ ] Create account management microservice with Flask (without integrated Swagger)
- [ ] Configure account service to expose OpenAPI JSON specification endpoint
- [ ] Implement User model with proper database schema and indexes
- [ ] Create database initialization and table creation logic
- [ ] Implement secure password hashing with Argon2
- [ ] Set up JWT token management (access + refresh tokens with proper expiration)

### Phase 3: Authentication Endpoints
- [ ] Create user registration endpoint with comprehensive input validation
- [ ] Create user login endpoint with authentication and rate limiting
- [ ] Create token refresh endpoint with rotation strategy
- [ ] Implement forgot password functionality with secure email tokens
- [ ] Create password reset endpoint with token validation

### Phase 4: Security & Infrastructure
- [ ] Add rate limiting for all security-sensitive endpoints
- [ ] Implement CORS configuration and security headers
- [ ] Add comprehensive input validation, sanitization, and SQL injection protection
- [ ] Create environment configuration management with secrets
- [ ] Set up database connection pooling and error handling
- [ ] Add health check and status endpoints for account service

### Phase 5: TypeScript Swagger Service
- [ ] Create separate TypeScript/Node.js Swagger aggregation microservice for centralized API documentation
- [ ] Configure TypeScript Swagger service to discover and aggregate multiple microservices
- [ ] Implement service discovery with proper TypeScript interfaces and types
- [ ] Set up TypeScript build pipeline and development workflow for Swagger service

### Phase 6: Testing & Deployment
- [ ] Test Docker container setup and multi-container orchestration
- [ ] Add logging and monitoring capabilities

## Future Extensibility

This architecture is designed to easily accommodate additional microservices:

- **Product/Inventory Service**
- **Order Management Service**
- **Notification Service**
- **Payment Service**
- **Analytics Service**

Each new service only needs to:
1. Expose an OpenAPI specification endpoint
2. Provide health check endpoint
3. Register in the Swagger service configuration

The TypeScript Swagger aggregator will automatically discover and document the new services, providing a unified API documentation experience.

---

**Access Points After Implementation:**
- **Main API Documentation**: http://localhost:3000
- **Account Service**: http://localhost:5000
- **Database**: postgresql://localhost:5432/account_db

This comprehensive plan provides a robust, secure, and scalable foundation for a microservices ecosystem with excellent developer experience through centralized, type-safe API documentation.