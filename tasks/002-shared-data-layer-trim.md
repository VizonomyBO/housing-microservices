# Task: Trim Shared Data Layer for Text-Only RAG (Deprecate Graph)

Follow `.kilocode/rules/memory-bank-instructions.md`, `AGENTS.md`, and `packages/shared_data_layer/AGENTS.md`; create/update a plan + tracker in the repo root.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Align shared data layer schemas/repos with the text-only voyage-context-3 stack, while deprecating graph-RAG structures by making conflicting fields nullable and clearly documented as deprecated.

## Scope
- Update models/migrations/schemas/factories/tests under `packages/shared_data_layer` to:
  - Support voyage-context-3 embeddings with configurable output_dimension (default 1024) across chunks/indexing; ensure Vector column sizing and validation follow the chosen dim.
  - Mark graph-RAG tables (graph_entities/edges/evidence/communities, workflow_*) and related constraints as nullable/deprecated rather than removed; add docstrings/comments/README notes calling out deprecation.
  - Ensure ownership semantics allow nullable owner and the shared sentinel (“0000”/system owner) without breaking existing constraints.
  - Flag non-text chunk fields (image_caption, schema_summary, table_payload, bbox) as deprecated/not used in the new pipeline; ensure ingestion/agent consumers focus on text content and metadata.
  - Keep document/ingestion enums consistent with synchronous pipeline; adjust metadata defaults if needed for voyage-context-3 normalization.
- Ensure repositories and tests drop assumptions about cache/rate-limit/graph usage and pass with new defaults.

## Deliverables
- Updated schema/models with voyage-context-3-friendly embedding config and deprecated graph/non-text fields clearly marked.
- Migration adjustments (or single migration update) applied to the existing revision file with test coverage/factories updated.
- README/docs in the package updated to reflect deprecations and new embedding dimension handling.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`, `packages/shared_data_layer/AGENTS.md`
