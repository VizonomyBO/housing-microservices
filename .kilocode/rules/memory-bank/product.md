# Product Overview

The Housing Microservices Platform is a production-ready ecosystem designed to provide secure authentication, robust user management, and centralized API documentation aggregation. It serves as a foundational platform for building scalable, secure, and observable microservices applications.

## Problem Statement
Building microservices often involves repeating boilerplate code for authentication, user management, and documentation. This platform solves this by providing:
- A centralized, secure authentication service.
- A dedicated user management service.
- An aggregated documentation portal to view all service APIs in one place.
- A shared data layer for consistent data access and persistence.

## Core Goals
1.  **Security**: Implement industry-standard security practices (Argon2id hashing, JWT with rotation, rate limiting, input validation).
2.  **Scalability**: Design for horizontal scaling with stateless authentication and connection pooling.
3.  **Observability**: Provide comprehensive health checks, metrics, and logging.
4.  **Developer Experience**: Simplify development with a shared data layer, unified documentation, and clear project structure.

## Key Features

### Authentication & User Management
-   **Secure Auth**: Argon2id password hashing, JWT access/refresh tokens with rotation.
-   **User Operations**: Registration, login, password reset, token verification.
-   **Security Controls**: Rate limiting, CORS, SQL injection prevention, XSS protection.

### API Documentation
-   **Aggregated Docs**: Centralized Swagger UI for all microservices.
-   **Service Discovery**: Automatic discovery of service specs.
-   **Health Monitoring**: Dashboard for service status and health metrics.

### Data & Ingestion
-   **Shared Data Layer**: Unified access to database models and repositories.
-   **Ingestion Service**: Processes documents (MarkItDown), chunks, embeds, and indexes data for RAG applications.
-   **Vector Search**: PostgreSQL with pgvector for semantic search capabilities.

## User Experience
-   **Developers**: Easy access to API documentation, standardized patterns for adding new services.
-   **End Users**: Secure and reliable account management, fast response times.
