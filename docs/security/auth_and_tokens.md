# Authentication, Authorization, and Tokens

## Overview
This document defines how the Housing Service and API Gateway handle user identity, tokens, and authorization. We rely on an upstream User Service for identity management and do not use AWS IAM roles for application-level authorization.

## Token Handover & Identity
- **Upstream Handover**: The upstream User Service authenticates users and issues a JWT (or equivalent secure token). This token is passed to the API Gateway in the `Authorization` header (e.g., `Bearer <token>`).
- **Gateway Responsibility**: The API Gateway validates the token signature and expiration. It extracts the `user_id` and other relevant claims.
- **Context Propagation**: The `user_id` is propagated to downstream services (Housing Service, Agents) via internal headers (e.g., `X-User-ID`).

## JWT Validation Implementation

### Library & Algorithm
- **Library**: `PyJWT`
- **Algorithm**: HS256 using `JWT_SECRET_KEY` (`AUTH_SHARED_SECRET` shared with downstream services)
- **Validation Paths**: Auth-service validates tokens directly (`verify_token_direct`); other services call `/v1/auth/verify-token` or verify locally with the shared secret.

### Claims Validation
The following JWT claims are validated on every request:
- **`exp` (Expiration)**: Token must not be expired (reject with 401)
- **`sub` or `user_id`**: Extracted as `user_id` for context propagation/ownership
- **`iss`/`aud` (Optional)**: Only enforced when explicitly configured upstream; default HS256 path does not require them

### FastAPI Dependency Pattern
```python
import jwt

def verify_token(token: str, secret: str):
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    return {
        "user_id": payload.get("user_id") or payload.get("sub"),
        "roles": payload.get("roles", [payload.get("role")] if payload.get("role") else []),
    }
```

## Required Claims
The token MUST contain the following claims:
- `sub`/`user_id`: The unique `user_id` (propagated as owner_id; shared flows may use null/`"0000"` downstream)
- `exp` (Expiration): Token expiration timestamp.
- `roles` (Optional): List of user roles if applicable for coarse-grained access control.

## Persistence
- **User ID Only**: We persist ONLY the `user_id` in our databases (PostgreSQL, Vector DB) to reference user ownership of documents and conversations.
- **No PII**: We do not store PII (Personally Identifiable Information) like names or emails within the Housing Service. If needed, these are fetched from the User Service using the `user_id`.

## Request Guards & Quotas
- **Cache-free**: Distributed rate limiters and cache layers (SlowAPI/Valkey) are removed in the simplified stack.
- **Lightweight guards**: Auth-service uses an in-process guard per endpoint scope, keyed by client host, to cap bursts (e.g., register 5/min, login 10/min, refresh 20/min; reset/change/forgot-password guarded hourly). Controlled via `ENABLE_SIMPLE_GUARDS`.
- **Behavior**: Exceeding a guard returns HTTP 429; state is memory-only and bypassed in tests (`ENABLE_SIMPLE_GUARDS=false`).
- **Downstream services**: Rely on upstream platform/WAF quotas or simple per-endpoint guards instead of shared caches.

## Authorization & Roles
- **Handcrafted Roles**: We utilize a custom role-based access control (RBAC) system defined by the User Service.
    - Roles (e.g., `admin`, `resident`, `auditor`) are passed in the token or fetched from the User Service.
    - The Housing Service enforces permissions based on these roles (e.g., only `admin` can delete shared base documents).
- **No IAM Roles**: We explicitly **DO NOT** use AWS IAM roles or policies for user authorization within the application logic. IAM is strictly for infrastructure permissions (e.g., service-to-service access to S3 or DynamoDB), not for defining user privileges.
