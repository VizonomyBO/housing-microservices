# Design Documents

This directory contains the comprehensive design specifications for the Vizonomy platform.

## 📚 Reading Guide

We recommend reading the documents in the following order to build a progressive understanding of the system:

1.  **[System Architecture](overview/system_architecture.md)**: Start here. This document provides the high-level overview of the platform, core components, and data flow.
2.  **[Agent Architecture](agents/architecture.md)**: Dive into the LangGraph-based agent design, including the router, subgraphs, and state management.
3.  **[Schema & Persistence](data/schema_and_persistence.md)**: Understand the data model, including the dual-scope document system (base vs. user), deduplication logic, and knowledge graph tables.
4.  **[API Contracts](interfaces/api_contracts.md)**: Review the REST API specifications and event payloads that define the interface between the FastAPI Gateway and the LangGraph service.

## 📂 Directory Structure

*   **[overview/](overview/)**: High-level system design, architecture diagrams, and project status.
    *   `system_architecture.md`: The main design document (now holds inline PlantUML + Mermaid diagrams).
    *   `project_status.md`: Tracks pending definitions and roadmap items.
    *   `diagrams/`: Historical notes on diagram sources plus guidance for previewing the inline code blocks.
*   **[agents/](agents/)**: Detailed specifications for the AI agents.
    *   `architecture.md`: High-level agent design.
    *   `implementation.md`: Low-level implementation details (nodes, edges, state schema).
    *   `rag_blueprint.md`: Specifics of the RAG retrieval flow.
    *   `retrieval_config.md`: Configuration parameters for the retrieval system.
*   **[data/](data/)**: Database design and knowledge graph specs.
    *   `schema_and_persistence.md`: Detailed ERD and persistence rules.
    *   `knowledge_graph.md`: Primer on the GraphRAG implementation.
*   **[interfaces/](interfaces/)**: API and event definitions.
    *   `api_contracts.md`: REST API and event envelopes.
    *   `chat_response_rendering.md`: Frontend parsing and citation rendering guide for `/v1/chat` responses.

## 🚦 Status & Roadmap

For a current view of pending work, completed definitions, and the implementation roadmap, please refer to **[Project Status](overview/project_status.md)**.

## 🔧 Patch Deploys (Python services on EC2)

Use this flow to hot-patch running containers (agent-api/auth-service/user-service) without a full redeploy:

1) Prep env + SSH: `env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a`. Use the PEM from `ArchaaS/dist/vizonomy-v2-ec2-dev2.pem` and host `POSTGRES_HOST` from `.env.prod`. Quick check: `ssh -i ArchaaS/dist/vizonomy-v2-ec2-dev2.pem ec2-user@${POSTGRES_HOST} "echo ok && uptime"`.
2) Copy patched file to EC2: `scp -i ArchaaS/dist/vizonomy-v2-ec2-dev2.pem path/to/local_file.py ec2-user@${POSTGRES_HOST}:/tmp/local_file.py`.
3) Copy into the container: find the container name with `sudo docker ps --format '{{.Names}}' | grep agent-api` (or auth/user). Then `sudo docker cp /tmp/local_file.py <container>:/app/services/agent-api/src/.../file.py`.
4) Restart the service: `sudo docker compose -f /opt/housing-microservices/docker-compose.ec2.yml restart agent-api` (swap service name as needed). Wait for health: `sudo docker ps --format '{{.Names}} {{.Status}}' | grep agent-api`.
5) Verify: hit the service health (`curl http://localhost:8000/health` from EC2 or `${AGENT_BASE_URL}/health` remotely) and re-run a targeted `/v1/chat` or smoke script. Keep evidence under `/tmp/aws_smoke_step9/` when applicable.

Notes:
- Do not redeploy or rebuild images for small code patches; only copy the changed files and restart the affected container.
- Avoid chunk IDs or internal metadata in user-facing responses when patching agent-api; keep evidence structured in citations/table_results.
