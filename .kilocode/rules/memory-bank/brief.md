# Project Brief: Housing Microservices Platform

## Overview
The Housing Microservices Platform is a production-ready ecosystem designed for secure authentication, user management, and API documentation aggregation. It features a FastAPI Agent API, Flask-based authentication and user services, a FastAPI ingestion service, and a Node.js/Express Swagger aggregator. The platform is built with Docker for multi-container orchestration and uses PostgreSQL for robust data persistence.

## Key Components
- **Agent API (FastAPI + LangGraph)**: Handles chat, SSE, documents, and attachments.
- **Ingestion Service (FastAPI)**: Processes MarkItDown, chunks, embeds, and indexes data.
- **Auth Service (Flask)**: Manages user authentication and issues JWTs.
- **User Service (Flask)**: Handles user management.
- **Swagger Service (Node.js/Express)**: Provides an optional aggregated API documentation portal with interactive Swagger UI. **Note: The Swagger service is currently not deployed.**
- **PostgreSQL (pgvector 16)**: The primary database for both housing and authentication data.
- **Docker & Docker Compose**: For local development, testing, and production deployments.

## Technology Stack
- **Backend**: Python 3.11 (Flask, FastAPI, SQLAlchemy, Argon2-cffi, PyJWT, Flask-Limiter), PostgreSQL 15.
- **Frontend/Aggregator**: TypeScript 5.3, Node.js 20, Express.js, Swagger UI Express, Axios, Winston.
- **Infrastructure**: Docker, Docker Compose, Kubernetes (GKE, EKS, AKS), AWS (ECS/Fargate), Google Cloud, Azure.

## Features
- **Security**: Argon2id password hashing, JWT with HS256 signing (15-minute access tokens, 30-day refresh tokens with rotation), rate limiting, input validation, SQL injection prevention, XSS protection, CORS configuration, network isolation, non-root containers, health monitoring, secrets management.
- **Scalability**: Stateless authentication, horizontal scaling readiness, connection pooling, database indexing, async health monitoring, spec caching.
- **Observability**: Health check endpoints, service status dashboard, health metrics tracking, Winston logging, response time tracking, success rate monitoring.

## Deployment & Environments
The platform supports various deployment environments:
- **Local Development**: Using Docker Compose with LocalStack for AWS mocks. **Note: LocalStack setup is currently broken.**
- **Dev Hybrid**: Local services (auth, agent) connected to a cloud data plane (e.g., AWS RDS, S3).
- **Production**: Docker Compose, Kubernetes (with detailed YAML configurations for PostgreSQL, Auth Service, and Swagger Service), and major cloud providers (AWS, Google Cloud, Azure).
- **Patch Deploys**: A streamlined process for hot-patching running Python services on EC2 without full redeploys.

## Quick Start
1. Clone the repository and copy `env.example` to `.env`.
2. Choose a Docker Compose profile (`reduced` for Agent API demo, `full` for all services, or `default` for legacy auth/user/swagger).
3. Launch services using `docker compose up --build` with the chosen profile.
4. Verify health checks and access API docs. **Note: Swagger UI is not currently available.**

## Testing
- An API testing script (`test-api.sh`) is provided for manual testing of all major endpoints.
- Quality gates for `agent-api` include `ruff format`, `ruff check --fix`, `ty check`, and `pytest -n auto`.

## Documentation
Comprehensive documentation is available in the `docs` directory, covering system architecture, agent architecture, schema and persistence, and API contracts.

## Project Status
The project is considered production-ready, with all core phases completed successfully. Future plans include adding email services, user email verification, unit/integration tests, CI/CD, more microservices, API gateway, Redis caching, and a full monitoring stack.
