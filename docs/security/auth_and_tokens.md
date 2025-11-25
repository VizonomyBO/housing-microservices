# Authentication, Authorization, and Tokens

## Overview
This document defines how the Housing Service and API Gateway handle user identity, tokens, and authorization. We rely on an upstream User Service for identity management and do not use AWS IAM roles for application-level authorization.

## Token Handover & Identity
- **Upstream Handover**: The upstream User Service authenticates users and issues a JWT (or equivalent secure token). This token is passed to the API Gateway in the `Authorization` header (e.g., `Bearer <token>`).
- **Gateway Responsibility**: The API Gateway validates the token signature and expiration. It extracts the `user_id` and other relevant claims.
- **Context Propagation**: The `user_id` is propagated to downstream services (Housing Service, Agents) via internal headers (e.g., `X-User-ID`).

## JWT Validation Implementation

### Library & Algorithm
- **Library**: `python-jose[cryptography]` (v3.3+)
- **Algorithm**: RS256 (asymmetric, RSA public/private key pair)
- **Public Key Source**: JWKS (JSON Web Key Set) endpoint from User Service
    - Example: `https://user-service.internal/auth/.well-known/jwks.json`
    - **Caching**: Public keys cached for 1 hour (reduce upstream calls)

### Claims Validation
The following JWT claims are validated on every request:
- **`exp` (Expiration)**: Token must not be expired (reject with 401)
- **`sub` (Subject)**: Extracted as `user_id` for context propagation
- **`iss` (Issuer)**: Must match expected User Service identifier
- **`aud` (Audience)**: (Optional) Validates token is intended for Housing Service

### FastAPI Dependency Pattern
```python
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token: str = Depends(security)):
    try:
        payload = jwt.decode(
            token.credentials,
            public_key,  # From JWKS endpoint
            algorithms=["RS256"],
            issuer="user-service",
            audience="housing-service"  # Optional
        )
        return payload["sub"]  # user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

## Required Claims
The token MUST contain the following claims:
- `sub` (Subject): The unique `user_id`.
- `exp` (Expiration): Token expiration timestamp.
- `roles` (Optional): List of user roles if applicable for coarse-grained access control.

## Persistence
- **User ID Only**: We persist ONLY the `user_id` in our databases (PostgreSQL, Vector DB) to reference user ownership of documents and conversations.
- **No PII**: We do not store PII (Personally Identifiable Information) like names or emails within the Housing Service. If needed, these are fetched from the User Service using the `user_id`.

## Rate Limiting
- **Identity Consumption**: The centralized rate limiter uses the `user_id` (extracted from the token) as the key to track and enforce limits.
- **Policy**: Rate limits are applied per user, not per IP, to ensure fair usage across devices.

### Rate Limiting Implementation

- **Algorithm**: Token bucket (allows burst traffic while enforcing average rate)
- **Storage**: Valkey (Redis-compatible) - Distributed state across API instances
- **Library**: `slowapi` (FastAPI-native) or custom middleware
- **Key Format**: `ratelimit:{user_id}:{endpoint_group}` (e.g., `ratelimit:uuid:search`)

### Rate Limit Tiers
| User Role | Requests/Minute | Burst Allowance |
|-----------|-----------------|------------------|
| Standard  | 100             | 120              |
| Premium   | 500             | 600              |
| Admin     | Unlimited       | N/A              |

### Response Headers
When rate limit is hit:
- **HTTP Status**: 429 Too Many Requests
- **Headers**:
    - `Retry-After`: Seconds until limit resets
    - `X-RateLimit-Limit`: Max requests per window
    - `X-RateLimit-Remaining`: Requests remaining in current window

**Example Integration**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=lambda: get_user_id_from_token())
app.state.limiter = limiter

@app.get("/search")
@limiter.limit("100/minute")  # Standard tier
async def search_documents(...):
    ...
```

## Authorization & Roles
- **Handcrafted Roles**: We utilize a custom role-based access control (RBAC) system defined by the User Service.
    - Roles (e.g., `admin`, `resident`, `auditor`) are passed in the token or fetched from the User Service.
    - The Housing Service enforces permissions based on these roles (e.g., only `admin` can delete shared base documents).
- **No IAM Roles**: We explicitly **DO NOT** use AWS IAM roles or policies for user authorization within the application logic. IAM is strictly for infrastructure permissions (e.g., service-to-service access to S3 or DynamoDB), not for defining user privileges.
