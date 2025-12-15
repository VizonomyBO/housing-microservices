# Task 03 — InputNormalizer & AttachmentScopeLoader Nodes

## System Snapshot
- Tasks 01–02 delivered `AgentState` typing and checkpoint persistence (`services/agent-api/src/state/*`, `.../repositories/AgentCheckpointRepository.ts`).
- Retrieval nodes do not exist yet; you will introduce the first layer that prepares normalized inputs and attachment context.
- Shared data layer exposes document/workflow readers (see `packages/shared_data_layer/documents` and `.../workflows`).

## What You Inherit
- Stable checkpoint APIs for storing state between nodes.
- Database tables populated via previous epics (vector store, document metadata, workflow drafts).

## Goal
Implement LangGraph nodes that normalize incoming chat requests and preload attachment/workflow scopes before deeper retrieval.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.2 (retrieval pipeline overview).
2. `docs/agents/implementation.md` §3.1 (input handling, attachments, base-document auto attach rules).
3. `docs/data/schema_and_persistence.md` §3.3 (document metadata, `conversation_documents`).
4. `docs/interfaces/api_contracts.md` §3.1 (chat request payload fields that feed InputNormalizer).

## Implementation Scope & Files
- Nodes live under `services/agent-api/src/nodes/retrieval/`:
  - `input_normalizer_node.py`
  - `attachment_scope_loader_node.py`
- Shared utilities under `services/agent-api/src/nodes/retrieval/utils/` if needed.
- Tests under `services/agent-api/tests/nodes/retrieval/`.
- Update `docs/agents/implementation.md` retrieval section to mention these nodes and their responsibilities.

## Step-by-Step Instructions
1. **InputNormalizer**:
   - Accept raw chat request (includes user text, attachments, workspace/tenant id).
   - Enforce normalization: trim text, detect language, tag intent hints.
   - Validate attachments referencing `conversation_documents`; auto-attach base documents per rule in `docs/agents/implementation.md` §3.1.
   - Emit normalized payload (`normalized_prompt`, `tenant_scope`, `attachment_refs`).
2. **AttachmentScopeLoader**:
   - Receive normalized payload.
   - Fetch documents/workflows referenced by attachments using shared data layer clients.
   - Verify visibility and mark missing assets.
   - Output structure containing `documents`, `workflows`, and `warnings` for downstream nodes.
3. **Error Handling**:
   - Raise guardrail-ready errors (structured) if attachments fail validation; include codes for Router/HumanGate later.
4. **Testing**:
   - Input normalization scenarios (extra whitespace, different languages, missing attachments).
   - Attachment loader verifying base auto-attach and visibility enforcement.
   - Ensure outputs are deterministic for identical inputs.
5. **Docs**:
   - Describe how these nodes slot into the LangGraph diagram and what data they pass to GraphRetriever.

## Definition of Done
- Two nodes exported with LangGraph-compatible signatures (likely functions returning state update objects).
- Tests cover normalization + attachment loading edge cases.
- Documentation updated with node descriptions and data contracts.

## Handoff Notes
- Provide example payload (before/after normalization) for next agent implementing GraphRetriever.
- List any TODOs or extension points (e.g., language detection library choice).
