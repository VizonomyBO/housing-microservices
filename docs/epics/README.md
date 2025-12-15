# Implementation Roadmap

This directory contains the Epics required to build the Vizonomy system.

## Recommended Execution Order

### Phase 1: Foundation (Weeks 1-2)

- **Execute [Epic 1: Shared Data Layer](01.md)**
    - **Why**: API, Agent, and Workers all import this. Nothing works without the database models.

### Phase 2: Ingestion (Weeks 2-3)

- **Execute [Epic 2: Ingestion Pipeline](02.md)**
- **Execute [Epic 6: Infrastructure](06.md)** (Task 6.1 only - DB/S3 setup)
    - **Why**: You need data in the database to test the agent.

### Phase 3: The Brain (Weeks 3-5)

- **Execute [Epic 3: Agent Core](03.md)**
    - **Why**: Build the logic in isolation using unit tests and the data ingested in Phase 2.

### Phase 3.5: Reduced Scope MVP (Week 5)

- **Execute [Epic 3.5: Reduced Scope MVP Adaptation](035.md)**
    - **Why**: Provides a demo-ready, text-only build that keeps the advanced architecture (images, tables, rate limits) intact but bypassed until after the management review.

### Phase 4: Service Layer (Weeks 5-6)

- **Execute [Epic 4: API Gateway](04.md)**
    - **Why**: Expose "The Brain" to the outside world.

### Phase 5: Background Tasks (Week 7)

- **Execute [Epic 5: Async Workers](05.md)**
    - **Why**: Add PDF export and batch processing features.

### Phase 6: Production Launch (Week 8)

- **Execute remaining [Epic 6: Infrastructure](06.md) tasks**

### Phase 7: Authentication Enhancements (Week 8-9)

- **Execute [Epic 7: Authentication Email Service](07.md)**
    - **Why**: Enable email verification (confirm registration), password recovery, and password change notifications. Requires SES infrastructure (Terraform) and auth-service integration. Can be executed in parallel with Phase 6.
