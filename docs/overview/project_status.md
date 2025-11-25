<!-- markdownlint-disable MD013 MD022 MD032 -->

# Design Deep Dive

## Final Recommendation: FastAPI Gateway + LangGraph Service
- **Gateway duties** now live inside a FastAPI application (served by uvicorn/gunicorn). Async handlers, HTTP/2 SSE streaming, and Python-native auth/rate-limit middleware let us terminate TLS, enforce policy, and expose `/v1/*` routes without context switches to another runtime. If sustained concurrency demands it, we can still re-platform the outer API into Go later by reusing the same REST contracts.
- **Agentic / ML workloads** continue to run in Python (LangGraph + tool stack). Co-locating the gateway and agent service in the same FastAPI process means we can share Pydantic models, DB clients, and caching primitives while keeping workload-specific routers (agent vs. ingestion vs. admin) isolated with dependency injection.
- **Platform decomposition**: Within FastAPI we maintain separate routers for north-south traffic and internal callbacks, plus background task pools for ingestion + async jobs. Future Go migration simply swaps the north-south router while keeping the LangGraph ASGI app mounted internally.

## Pending Definition Work

### 1. API & Event Contracts
- Completed in [interfaces/api_contracts.md](../interfaces/api_contracts.md), covering the REST schemas (`system_architecture.md:244-254`), ingestion event payloads, and LangGraph envelopes end-to-end.

### 2. Authentication, Authorization, and Tokens
- Define how upstream services hand over user tokens, which claims are required, how we persist only the `user_id` reference, and how the centralized rate limiter consumes those identities.
- Document IAM scopes/roles for the FastAPI surface (public VPC) versus the internal workers/background tasks, and note any mTLS or signed request requirements for cross-service callbacks.

### 3. Database Schema & Persistence Rules
- Completed in [data/schema_and_persistence.md](../data/schema_and_persistence.md), now covering user-owned docs, country-scoped base docs, hash deduplication, `conversation_documents` ref-counting, and the garbage-collection rules other workstreams must respect.

### 4. Retrieval & Agent Configuration
- Completed in [agents/retrieval_config.md](../agents/retrieval_config.md), locking down the configuration knobs (`hybrid_k`, RRF windows, reranker limits, loop/repair thresholds, cache TTLs, chunking) along with fallback logic, score/metric emission, and the rules for merging base + user documents with `visibility_override`.

### 5. Asynchronous Jobs & Queues
- Describe SQS (or alternative) payloads, deduplication keys, job status lifecycle, and retry/backoff policies for the Pillar Answer engine and PDF export worker.
- Enumerate monitoring/alerting requirements for these background flows.
- Define how queue payloads reference the resolved document set (base + user) so async jobs respect the same ref-counting guarantees when generating outputs or performing cleanup.

### 6. Inter-Service Communication Details
- Decide when REST is sufficient vs. where gRPC (or messaging) should land, list serialization formats, and outline the migration path if/when we introduce protobuf contracts.
- Define health checks, timeout budgets, and backpressure behavior between the FastAPI gateway threads, LangGraph async tasks, and any sidecar processes we add later (e.g., dedicated retrieval workers).

### 7. Observability & Operations
- Establish logging structure, tracing spans per LangGraph node, metrics (latency, success, retries, embeddings/sec), and alert thresholds for both services.
- Write the operations runbook (deploy, rollback, hotfix, on-call escalation) and plan for structured dashboards.
- Add dashboards for document dedup hit rate, `conversation_documents` churn, base-doc ref counts, and GC backlog so ops can detect leaks/deletions.

### 8. Infrastructure & Deployment
- Translate the hybrid EC2 + Lambda design into IaC modules (VPC layout, subnets, autoscaling policies, AMIs/containers).
- Define CI/CD steps for both languages, artifact promotion gates, blue/green or canary strategy, and secrets management flow.

### 9. Security & Compliance
- Detail encryption in transit/at rest, Secrets Manager/KMS policies, data retention windows, audit logging, and PII handling that honors the “store only user_id” constraint.
- Assess vulnerability scanning, dependency pinning, and threat-model coverage (prompt-injection defenses, guardrails).
- Define RBAC/RLS for base-document management UI, audit trails for admin deletes, and safeguards so chat-driven deletion paths can’t remove shared/base documents.

### 10. Testing & Validation
- Outline contract tests for the REST APIs, gRPC/REST interop tests, migration tests for the DB schema, ingestion replay tests, retrieval-quality benchmarks, and load testing plans for rate limiting plus cache behavior.
- Define fixtures/datasets needed to validate citations, numerical tooling, and PDF outputs end-to-end.
- Add coverage for document dedup (same hash, multi-chat refs), base-doc attachment toggles, and GC/ref-count edge cases so regressions surface early.
