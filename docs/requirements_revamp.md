# Requirements Revamp (Current vs. Target)

## Purpose
- Capture the new simplified design (auth, user, ingestion, agent) and contrast it with the existing LangGraph/caching/multimodal stack so we can remove legacy pieces and rebuild the core flows without backward compatibility. Retain the shared data layer; deprecate unused pieces, relax dead-end relations to nullable, and note deprecated entities explicitly.

## Current State (baseline to replace)
- Agent API uses LangGraph workflows with hybrid retrieval (BM25 + vector + Voyage rerankers), citation enforcement, attachment gating, and Valkey-backed cache/rate limiter hooks (see docs/overview, docs/agents, AGENTS.md, README.md).
- Ingestion service expects MarkItDown extraction with chunk/embed/index/activation, previously replacing a Lambda/S3 path but still shaped for multi-stage async workflows and attachment gating.
- Auth and user services are Flask-based; Swagger aggregator (Node/TS) exists but is optional/disabled.
- Compose footprints include reduced/full/hybrid profiles with LocalStack, Valkey, telemetry, and multiple env files; prod deploy scripts target EC2 with the legacy stack.
- Documentation covers epics, reduced-scope modes, cache/rate limiter wiring, and prior Lambda/S3 history; several task plans and agent prompts remain.

## Target Architecture (what we want)
- Services: Auth service (Flask), User service (Flask), Ingestion service (FastAPI, text-only sync), Agent service (FastAPI) using a simplified ReAct agent with tools plus `langchain_sandbox` Pyodide runner for code execution (source: https://github.com/langchain-ai/langchain-sandbox; allows PyodideSandboxTool with optional stateful sessions and network installs).
- Retrieval/RAG: text-only ingestion and retrieval RAG (graph RAG removed); use Voyage `voyage-context-3` embeddings (default 1024 dims; supports 256/512/2048) and `rerank-2.5`. Voyage embeddings are length-normalized (cosine/dot equivalent) per docs. Apply advanced RAG techniques (HyDE/HyPE-style query expansion, contextual chunk headers, proposition/semantic chunking, fusion retrieval + BM25/vector, reranking, multi-faceted filtering, hierarchical/parent-child summaries) inspired by https://github.com/NirDiamant/RAG_Techniques.
- Tools for the ReAct agent: retrieval (BM25/vector over Postgres/pgvector with rerank-2.5), rerank utility, document status/activation, attachment management, and a Pyodide code tool for computations/tabular work (per LangGraph ReAct patterns: https://langchain-ai.github.io/langgraph/how-tos/react-agent-from-scratch/).
- Storage: Postgres 16 + pgvector remains; single ingestion path writes chunks/embeddings synchronously. Shared data layer is retained; trim or mark unused relations nullable when they conflict with the simplified model and explicitly deprecate graph-RAG tables/fields rather than removing the package.
- Safety/quotas: No Valkey cache or rate limiter in the new design; rely on provider limits or simple app-side guards as needed.

## Required Removals (breaks allowed)
- Multimodal extraction, image/table ingestion code paths, and any MarkItDown variants for non-text.
- Lambda/S3 ingestion remnants, Step Functions cues, and upload proxy logic that assumes async activation.
- Valkey cache client, rate limiter integrations, cache observability, and related env vars/compose services.
- Graph RAG logic (planning, relationship traversal) and any graph-specific prompts/tasks; deprecate related schema fields (make nullable) rather than deleting the shared data layer.
- Old task plans/prompts/agent artifacts tied to LangGraph graph planner, workflows, reduced-scope/demo toggles, and cache/rate-limit gating.
- Legacy docker-compose profiles for full/reduced/hybrid that start LocalStack, Valkey, telemetry collectors, marker/worker helpers, or Step Functions simulators.
- Shell scripts and runbooks specific to the old stack (prod smoke for Lambda flows, cache/telemetry rollout, reduced-scope toggles).
- Docs describing cache TTLs, Valkey integration, Lambda ingestion, reduced-scope modes, graph RAG, and prior epics that no longer apply.

## Required Additions
- ReAct agent implementation with a focused tool suite:
  - Retrieval tool(s) over Postgres/pgvector (text chunks only) using voyage-context-3 embeddings and rerank-2.5.
  - Rerank utility and metadata filtering/multi-query helpers (HyDE/HyPE, query decomposition, fusion retrieval).
  - Document ingestion status/activation tool (if needed for grounding).
  - Attachment management tool (list docs, bulk attach/detach, ownership-aware).
  - Pyodide code execution tool (`PyodideSandboxTool`, optional stateful sessions) for computations and tabular analysis.
- Ingestion service rework for synchronous text-only pipeline: parse → chunk → embed (contextualized) → persist → activate; expose a single upload/ingest endpoint. Support Voyage output_dimension selection (default 1024; adjust DB column/dtype if needed) and note embeddings are normalized.
- Auth + User services (Flask): JWT issuance/verification plus user management; user-service remains.
- Ownership/attachments: endpoint to list documents; endpoint to create conversations; bulk attach/detach documents by ID; owner_id nullable/”0000” allows shared docs; uploads/edit can set owner/shared flag; allow deletes (DB + S3 + chunks).
- Environment definitions:
  - Dev: docker-compose that starts Postgres, auth, user, ingestion, agent, and LocalStack (S3/needed AWS mocks) in one stack; env file tuned to retained services only. LocalStack is required for S3 and any AWS services used in dev.
  - Prod: EC2 deployment of auth, user, ingestion, agent, and Postgres; fresh start/cleanup of old containers and configs.
- Documentation: new architecture overview, RAG/data flow for text-only ingestion, agent/tooling description (including Pyodide sandbox constraints: WebAssembly, no filesystem, httpx for network), LocalStack dev usage, and dev/prod runbooks aligned to the trimmed compose/deploy story.

## Required Changes (migrate/rewrite)
- Agent service: replace LangGraph graph planner/guardrails with a lean ReAct loop and the new tool set; remove cache/rate-limit dependencies; update prompts and evals to match ReAct behavior while preserving citation quality for text; incorporate advanced RAG techniques (HyDE/HyPE, contextual headers, fusion retrieval, multi-faceted filtering, rerank-2.5).
- Ingestion service: simplify to synchronous ingestion (no async jobs/activation polling), ensure contextualized embeddings (voyage-context-3) are built inline, re-ingest existing corpora, and adjust storage for chosen output_dimension/normalization; drop graph-edge creation and mark graph relations nullable/deprecated in the shared data layer.
- Auth/User: retain user-service; align auth + user flows with the simplified stack and shared auth_db; remove any coupling to deprecated cache/rate-limit layers.
- Data layer: keep the shared package; deprecate graph-RAG relations, mark unused relations nullable, and add new fields only via the shared data layer. Explicitly mark deprecated DB entities to avoid accidental reuse; leave unused artifacts in place but documented as deprecated.
- Dev/prod tooling: update compose files, env templates, and scripts to match the retained services (auth, user, ingestion, agent) with LocalStack for dev; remove profiles/flags for reduced/full/demo modes and Valkey/telemetry extras.
- CI/quality gates: adjust lint/test/type/eval suites to the new services and remove Valkey/rate-limit/cache and Lambda dependencies.
- Observability/runbooks: rewrite health checks, smoke tests, and deployment steps for the simplified stack (compose up, EC2 deploy) without cache/telemetry prerequisites.
- Deployment automation: add a script with flags for (a) full infra/app redeploy (terraform down/up + rebuild/redeploy services; exclude DB teardown/backups), (b) service-only redeploy (build/push Docker images and update only changed services on EC2), and (c) hot patch (ssh into EC2, patch files in the running container, restart service for quick validation). Protect full redeploy with explicit confirmation since it is destructive.

## Open Decisions to Clarify (follow-up)
- None pending from earlier prompts; implement above directives (shared data layer retained, graph RAG deprecated, voyage-context-3 + rerank-2.5, simplified ownership/attachments, LocalStack for dev compose). 
