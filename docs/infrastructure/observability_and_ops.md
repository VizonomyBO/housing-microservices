# Observability & Operations

> **Archived (pre-revamp):** Reflects the deprecated telemetry stack (OTEL collectors, cache metrics, Lambda traces). Current workflows rely on service health endpoints and smoke scripts; telemetry extras are not part of the supported stack.

## Overview
This document defines the observability strategy (Logging, Tracing, Metrics) and operational procedures (Runbooks) for the Housing Service. We adhere to OpenTelemetry (OTEL) standards for telemetry and use structured JSON logging.

## 1. Logging
- **Format**: Structured JSON.
- **Levels**: `INFO` (default), `WARN` (handled errors), `ERROR` (unhandled exceptions/critical failures), `DEBUG` (verbose dev mode).
- **Standard Fields**:
  ```json
  {
    "timestamp": "ISO8601",
    "level": "INFO",
    "service": "housing-service",
    "trace_id": "otel_trace_id",
    "span_id": "otel_span_id",
    "user_id": "uuid",
    "message": "Processing document upload",
    "context": { "document_id": "...", "file_size": 1024 }
  }
  ```
- **Context Injection**: Middleware automatically injects `trace_id` and `user_id` (from Auth token) into all log entries for request correlation.

## 2. Distributed Tracing
- **Standard**: OpenTelemetry (OTEL).
- **Instrumentation**:
  - **FastAPI**: Auto-instrumented for HTTP requests (latency, status codes).
  - **LangGraph**: Custom spans for each Node execution (Agent steps).
  - **Database**: Auto-instrumented for SQL queries (Postgres) and Vector searches.
  - **External APIs**: Spans for User Service and LLM provider calls.
- **Sampling**: 100% in Dev/Staging, 10% (probabilistic) in Production (adjustable).

## 3. Metrics & Dashboards

### 3.1 Business Metrics
- `ingestion_count_total`: Documents uploaded (labeled by `status`, `country`).
- `chat_sessions_total`: New conversations started.
- `cache_hit_rate`: Percentage of retrieval requests served from Valkey.
- `dedup_hit_rate`: Percentage of uploads resolved via content hash deduplication.

### 3.2 System Metrics
- `http_request_duration_seconds`: API Latency (p50, p95, p99).
- `error_rate`: Percentage of 5xx responses.
- `queue_depth`: SQS visible messages (Ingestion, Export).
- `langgraph_step_latency`: Time taken per agent node.
- `gc_backlog`: Number of soft-deleted items awaiting hard delete.

### 3.3 Dashboards
- **Overview**: Global health, error rates, active users.
- **Ingestion Pipeline**: Queue depth, processing latency, success/failure rates.
- **Retrieval Quality**: Cache hits, average citations per answer, user feedback scores (thumbs up/down).

## 4. Alerting
| Metric | Threshold | Severity | Action |
| --- | --- | --- | --- |
| API Error Rate | > 1% over 5m | P1 | Page On-Call |
| API Latency (p99) | > 2s over 5m | P2 | Notify Channel |
| Queue Depth | > 1000 msgs | P2 | Auto-scale / Notify |
| DLQ Volume | > 10 msgs/hr | P3 | Create Ticket |
| DB CPU | > 80% | P2 | Notify Channel |

## 5. Operations Runbook

### 5.1 Deployment
1. **CI Pipeline**: Run tests (Unit, Contract), Lint, Build Container.
2. **CD Pipeline**:
   - Deploy to **Staging**.
   - Run Integration Tests.
   - Promote to **Production** (Rolling Update).
   - Verify `/health/live` and `/health/ready`.

### 5.2 Rollback
- **Strategy**: Revert to previous Docker image or Launch Template version.
- **Trigger**: Error rate spike > 5% or P1 alert immediately post-deploy.
- **Command**: 
    - **EC2 ASG (Launch Template)**: Update ASG to use previous Launch Template version
      ```bash
      aws autoscaling update-auto-scaling-group --auto-scaling-group-name housing-service-asg \
        --launch-template LaunchTemplateName=housing-service,Version='$Previous'
      # Then trigger instance refresh or manual termination for rolling update
      ```
    - **EC2 ASG (Docker Image)**: SSH to instances and pull previous image tag
      ```bash
      # On each EC2 instance
      docker pull <ecr-repo>:PREVIOUS_SHA
      systemctl restart housing-service
      ```

### 5.3 Hotfix
1. Branch from `main`.
2. Fix bug & add test case.
3. Push to `hotfix/*` branch.
4. CI triggers "Fast Path" build (skips long load tests).
5. Manual approval to deploy to Production.

### 5.4 On-Call Escalation
- **Level 1**: Automated Alerts (PagerDuty/OpsGenie).
- **Level 2**: On-Call Engineer (triage, rollback, restart).
- **Level 3**: Tech Lead / Domain Expert (complex logic bugs).
