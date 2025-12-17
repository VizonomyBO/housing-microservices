# Task: Rework Ingestion Service for Synchronous Text-Only voyage-context-3

Follow `.kilocode/rules/memory-bank-instructions.md` and `AGENTS.md`; create/update a plan + tracker in the repo root.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Make the ingestion FastAPI service strictly text-only, synchronous, and aligned with voyage-context-3 embeddings (configurable output dimension), producing contextual chunks for the ReAct agent toolchain.

## Scope
- Update `services/ingestion-service` settings/pipeline/auth to:
  - Default to voyage-context-3 embeddings (1024 dim) with support for 256/512/2048 via config/request; honor Voyage length-normalized outputs.
  - Enforce text-only inputs (remove multimodal/MarkItDown variants, trim allowed source types accordingly) and apply contextual/proposition chunking (headers, HyPE/HyDE-style rewrites) before embed/index.
  - Keep synchronous upload → chunk → embed → persist → activate flow; remove/clean any async/polling hooks or legacy ingestion modes.
  - Ensure owner_id handling matches requirements (nullable/“0000” shared), dedupe semantics preserved, and metadata reflects new ingestion mode.
  - Agent API remains the upload front door: `/v1/documents/upload` proxies to ingestion, so keep the ingestion upload contract stable, enforce auth/owner semantics, and return the metadata agent-api uses for gating (document_id, ingestion_id, content_hash, status).
- Update tests/fixtures/config docs for the new model/dimension settings and text-only constraints.

## Deliverables
- Ingestion service code/config/tests reflecting synchronous text-only pipeline with voyage-context-3 embeddings and contextual chunking.
- Updated API validation (allowed source types, payload sizes, metadata) and documentation for the ingestion endpoints.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`
