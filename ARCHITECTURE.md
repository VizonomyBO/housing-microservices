# Architecture Documentation

## System Overview

This microservices platform implements a modern, scalable architecture with the following key components:

1. **Account Management Service** (Flask/Python) - Authentication and user management
2. **Swagger Aggregator Service** (TypeScript/Node.js) - Centralized API documentation
3. **PostgreSQL Database** - Data persistence
4. **Docker Environment** - Container orchestration

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        Client Layer                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │   Browser   │  │  Mobile App  │  │  External Services      │ │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    API Gateway / Load Balancer                    │
│                         (Future: Nginx/Traefik)                   │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Application Layer                             │
│                                                                   │
│  ┌────────────────────────────┐  ┌────────────────────────────┐ │
│  │  Swagger Aggregator        │  │   Account Service          │ │
│  │  (TypeScript/Express)      │◄─┤   (Flask/Python)           │ │
│  │  Port: 3000                │  │   Port: 5000               │ │
│  │                            │  │                            │ │
│  │  - Service Discovery       │  │   - User Authentication    │ │
│  │  - Spec Aggregation        │  │   - JWT Token Management   │ │
│  │  - Health Monitoring       │  │   - Password Reset         │ │
│  │  - Swagger UI              │  │   - Rate Limiting          │ │
│  └────────────────────────────┘  └────────────────────────────┘ │
│                                              │                    │
└──────────────────────────────────────────────┼────────────────────┘
                                               │
                                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Data Layer                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL Database                                        │  │
│  │  Port: 5432                                                 │  │
│  │                                                             │  │
│  │  Tables:                                                    │  │
│  │  - users (authentication data)                              │  │
│  │  - refresh_tokens (token management)                        │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Swagger Aggregator Service

**Technology Stack:**
- TypeScript 5.3+
- Node.js 20+
- Express.js
- Swagger UI Express
- Axios (HTTP client)
- Winston (Logging)

**Responsibilities:**
- Discover and register microservices
- Fetch OpenAPI specifications from services
- Aggregate multiple specs into unified documentation
- Monitor service health
- Provide interactive Swagger UI
- Track service metrics

**Key Classes:**

```typescript
ServiceDiscovery
├── Manages service registry
├── Performs health checks
├── Fetches OpenAPI specs
└── Caches service data

SpecAggregator
├── Merges multiple OpenAPI specs
├── Adds service prefixes to paths
├── Prevents component naming conflicts
└── Generates unified documentation

HealthMonitor
├── Periodic health checking
├── Collects service metrics
├── Tracks success rates
└── Monitors response times
```

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Landing page |
| GET | `/docs` | Interactive Swagger UI |
| GET | `/health` | Service health check |
| GET | `/api/services` | List all services |
| GET | `/api/specs` | Aggregated OpenAPI spec |
| GET | `/api/status` | System status |
| POST | `/api/refresh` | Force refresh |

### 2. Account Management Service

**Technology Stack:**
- Python 3.11+
- Flask 3.0
- SQLAlchemy (ORM)
- PostgreSQL
- Argon2 (Password hashing)
- PyJWT (Token management)
- Flask-Limiter (Rate limiting)

**Responsibilities:**
- User registration and authentication
- JWT token generation and validation
- Token refresh and rotation
- Password reset functionality
- User session management
- Security and rate limiting

**Architecture Layers:**

```python
API Layer (api/)
├── auth.py - Authentication endpoints
└── system.py - Health and documentation

Service Layer (services/)
├── auth_service.py - JWT and authentication logic
└── user_service.py - User management logic

Model Layer (models/)
├── user.py - User entity
└── refresh_token.py - Token tracking

Utility Layer (utils/)
├── security.py - Encryption and hashing
└── validators.py - Input validation
```

**Database Schema:**

```sql
users
├── id (PK)
├── email (UNIQUE)
├── username (UNIQUE)
├── password_hash
├── first_name
├── last_name
├── is_active
├── is_verified
├── created_at
├── updated_at
├── last_login
├── reset_token
└── reset_token_expires

refresh_tokens
├── id (PK)
├── user_id (FK → users.id)
├── token (UNIQUE)
├── is_revoked
├── created_at
├── expires_at
├── user_agent
└── ip_address
```

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Authenticate user |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/logout` | Revoke refresh token |
| POST | `/auth/forgot-password` | Request password reset |
| POST | `/auth/reset-password` | Complete password reset |
| POST | `/auth/verify-token` | Verify token validity |
| GET | `/health` | Service health |
| GET | `/openapi.json` | OpenAPI spec |

### 3. PostgreSQL Database

**Configuration:**
- Version: 15
- Connection pooling enabled
- Health checks configured
- Persistent volume for data

**Optimization:**
- Indexes on frequently queried columns
- Connection pool (10 connections)
- Pool pre-ping enabled
- Query optimization with ORM

## Security Architecture

### Authentication Flow

```
1. User Registration
   ├── Input validation (email, username, password)
   ├── Password strength check
   ├── Argon2 hashing
   └── Store in database

2. User Login
   ├── Credential verification
   ├── Argon2 password verification
   ├── Generate access token (15 min expiry)
   ├── Generate refresh token (30 day expiry)
   ├── Store refresh token in database
   └── Return both tokens

3. Token Refresh
   ├── Verify refresh token (JWT + DB check)
   ├── Revoke old refresh token
   ├── Generate new access token
   ├── Generate new refresh token
   └── Return new tokens

4. Token Verification
   ├── Decode JWT
   ├── Verify signature
   ├── Check expiration
   └── Return user info
```

### Security Measures

**Account Service:**
- Argon2id password hashing (memory: 64MB, iterations: 2)
- JWT with HS256 algorithm
- Token rotation on refresh
- Rate limiting (configurable per endpoint)
- Input validation and sanitization
- SQL injection prevention (SQLAlchemy ORM)
- CORS configuration
- Security headers (HSTS, CSP, X-Frame-Options)

**Infrastructure:**
- Docker network isolation
- Non-root container execution
- Health checks for automatic recovery
- Environment variable management
- Secrets not committed to repository

## Data Flow

### User Registration Flow

```
Client → POST /auth/register
    ↓
API Layer (auth.py)
    ↓
Rate Limiter (5 req/min)
    ↓
Input Validation
    ├── Email format
    ├── Username format
    └── Password strength
    ↓
UserService.create_user()
    ├── Check email uniqueness
    ├── Check username uniqueness
    ├── Hash password (Argon2)
    └── Create user record
    ↓
Database (PostgreSQL)
    ↓
Return user data ← 201 Created
```

### Login Flow

```
Client → POST /auth/login
    ↓
API Layer (auth.py)
    ↓
Rate Limiter (10 req/min)
    ↓
AuthService.authenticate_user()
    ├── Find user by email/username
    └── Verify password (Argon2)
    ↓
AuthService.generate_tokens()
    ├── Create access token (JWT)
    ├── Create refresh token (JWT)
    └── Store refresh token in DB
    ↓
Update last_login timestamp
    ↓
Return tokens ← 200 OK
```

### Swagger Aggregation Flow

```
Client → GET /docs
    ↓
Swagger Service
    ↓
Check cached specs
    ├── If cached → Use cache
    └── If not cached ↓
        ServiceDiscovery.fetchAllServiceSpecs()
            ├── Fetch from Account Service
            └── Fetch from other services
        ↓
        Cache specs
    ↓
SpecAggregator.mergeSpecs()
    ├── Add service prefixes
    ├── Merge paths
    ├── Merge components
    ├── Merge tags
    └── Create unified spec
    ↓
Swagger UI rendering
    ↓
Return HTML/UI ← 200 OK
```

## Scaling Considerations

### Horizontal Scaling

**Account Service:**
- Stateless design (JWT)
- Can run multiple instances
- Load balancer required
- Session data in database

**Swagger Service:**
- In-memory caching (consider Redis for multi-instance)
- Shared service registry
- Load balancer required

**Database:**
- Master-slave replication
- Read replicas for scaling reads
- Connection pooling

### Vertical Scaling

- Adjust Docker resource limits
- Database tuning (shared_buffers, work_mem)
- Connection pool sizing

### Performance Optimization

- Response caching (Swagger specs)
- Database query optimization
- Index optimization
- Connection pooling
- Async operations where possible

## Monitoring and Observability

### Health Checks

All services expose `/health` endpoint:
- Database connectivity
- Service status
- Response time
- Memory usage

### Metrics

**Swagger Service tracks:**
- Service health status
- Response times
- Success rates
- Uptime

**Account Service provides:**
- Request counts
- Error rates
- Active users
- Token operations

### Logging

**Log Levels:**
- ERROR: Critical issues
- WARN: Warning conditions
- INFO: General information
- HTTP: HTTP requests
- DEBUG: Detailed debugging

**Log Locations:**
- Console output (development)
- File logs (production)
- Future: ELK stack, CloudWatch

## Future Enhancements

### Planned Features

1. **API Gateway**
   - Nginx or Traefik
   - SSL/TLS termination
   - Request routing
   - Rate limiting

2. **Service Mesh**
   - Istio or Linkerd
   - Traffic management
   - Security policies
   - Observability

3. **Message Queue**
   - RabbitMQ or Kafka
   - Async operations
   - Event-driven architecture
   - Microservice communication

4. **Caching Layer**
   - Redis
   - Session storage
   - API response caching
   - Distributed locking

5. **Monitoring Stack**
   - Prometheus (metrics)
   - Grafana (visualization)
   - ELK Stack (logging)
   - Jaeger (tracing)

### Adding New Services

To add a new microservice:

1. Implement service with OpenAPI spec endpoint
2. Add health check endpoint
3. Register in `services/swagger-service/src/config/services.ts`
4. Add to `docker-compose.yml`
5. Documentation automatically appears in Swagger UI

## Deployment Strategies

### Development
- Docker Compose
- Local PostgreSQL
- Hot reload enabled

### Staging
- Docker Compose or Kubernetes
- Managed database
- SSL certificates
- Resource limits

### Production
- Kubernetes (GKE, EKS, AKS)
- Managed database (RDS, Cloud SQL)
- Auto-scaling
- High availability
- CDN for static assets
- Backup and disaster recovery

## Performance Benchmarks

**Expected Performance:**

| Metric | Target | Notes |
|--------|--------|-------|
| Auth API Response | < 200ms | p95 |
| Swagger UI Load | < 1s | First load |
| Database Queries | < 50ms | Simple queries |
| Health Checks | < 100ms | All services |
| Token Generation | < 100ms | JWT creation |

## Security Compliance

- OWASP Top 10 addressed
- Password requirements enforced
- Token expiration implemented
- Rate limiting configured
- Input validation comprehensive
- SQL injection prevention
- XSS prevention (headers)
- CSRF protection considerations

---

**Last Updated:** 2025-10-29
**Version:** 1.0.0

