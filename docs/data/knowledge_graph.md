<!-- markdownlint-disable MD013 MD022 MD032 -->

# Knowledge Graph & Workflow Graph Primer

## 1. Why This Matters Now
- **GraphRAG is part of the new router flow** (see `agent_design.md §2.2`). Analyst and Numerical routes now expect graph context (`graph_context`, `workflow_plan`) alongside the usual fused chunks.
- **Postgres-first implementation**: We are not adding a separate graph DB. Instead, the ingestion pipeline populates the new `graph_entities`, `graph_edges`, `graph_evidence`, and `graph_communities` tables plus workflow graph tables described in `schema_and_persistence.md`.
- **Downstream impact**: `GraphRetriever`, `GraphSummarizer`, and `WorkflowPlanner` nodes consume these tables directly. Anyone touching ingestion, retrieval, or analytics needs to understand how the data is structured and refreshed.

## 2. Knowledge Graph Basics
| Term | Definition | Implementation detail |
| --- | --- | --- |
| **Entity** | Canonical object extracted from text (e.g., “Liberia Ministry of Finance”, “CIT revenue growth”). | Row in `graph_entities` keyed by `(entity_type, entity_key)` with labels, properties, optional embeddings, provenance timestamps. |
| **Edge/Relationship** | Directed or undirected link between entities that captures “impacts”, “depends_on”, “reported_in”, etc. | Row in `graph_edges` referencing `source_entity_id`, `target_entity_id`; stores weight/confidence plus evidence chunk ids. |
| **Evidence** | Concrete passages backing an edge. | `graph_evidence` rows with chunk offsets for traceability; used for citations and auditing. |
| **Community / Cluster** | Group of entities tightly connected (Leiden/Louvain style) summarizing a theme. | `graph_communities` rows storing member entity ids, summary text, metrics, and algo version. |

### Extraction Flow
1. Ingestion runs entity + relation extraction (LLM/GNN) after chunking.
2. Entities upserted into `graph_entities`; embeddings computed via Voyage (dim 512).
3. Relations upserted into `graph_edges`; evidence rows inserted per linked chunk.
4. Nightly job recomputes communities and updates summaries (used by GraphSummarizer).
5. Pruning: entities/edges with no surviving evidence and `last_seen_at` > 18 months are removed.

## 3. Workflow Graph Concepts
| Term | Definition | Implementation detail |
| --- | --- | --- |
| **Workflow graph** | Versioned playbook (coarse/mid/fine) describing how experts triage incidents, budget questions, etc. | `workflow_graphs` table; each row has domain, country, status, semantic version. |
| **Node** | A single step with granularity (`coarse`, `mid`, `fine`) and metadata (preconditions, tool hints). | `workflow_nodes` linked to `workflow_versions` with `ltree path` (e.g., `triage.validate_data.check_ledger`). |
| **Edge** | Transition between nodes with type (`success`, `repair`, `clarification`). | `workflow_edges` referencing source/target nodes; includes confidence and constraints. |
| **Version history** | Auditable log of playbook changes. | `workflow_versions` ties together reviewers, diffs, timestamps. |

### How Plans Are Generated
- `WorkflowPlanner` selects the latest published graph for the user’s domain/country and walks the hierarchy to build a `workflow_plan` tailored to the question + graph context.
- Nodes contain `preconditions` referencing graph entities (e.g., “if entity.type = metric and country=LBR”) so plans stay grounded.
- Outputs feed Analyst/Numerical subgraphs, which can follow the plan verbatim, refine it, or request HITL assistance.

## 4. How Graph Data Is Used in the Agent
1. **GraphRetriever** queries `graph_entities`/`graph_edges` using the reranked chunks plus user intent (vector similarity + metadata filters).
2. **GraphSummarizer** composes human-friendly descriptions from `graph_communities.summary`, edge evidence, and freshness data.
3. **WorkflowPlanner**:
   - Maps the question to the correct workflow graph.
   - Selects the relevant coarse/mid/fine nodes using `ltree` queries.
   - Emits a structured plan referencing specific documents/entities so downstream LLM calls remain deterministic.
4. **Numerical subgraph** can reference the workflow plan (e.g., “Step 2: run Polars SQL on table Budget_2024”) and cite both table chunks and graph evidence.

## 5. Schema & Infrastructure Quick Reference
- **Extensions**: `pgvector`, `ltree`, `pg_trgm`, `pg_graphql`/`apache_age`, `pgcrypto`. Enabled cluster-wide; see `schema_and_persistence.md §3.8`.
- **Tables**: Full definitions live in `schema_and_persistence.md §3.9–3.10`.
- **APIs / Services**:
  - Ingestion workers call new internal endpoints to upsert entities/edges.
  - Graph maintenance job recomputes communities nightly.
  - Workflow graph authoring UI writes to `workflow_graphs` + `workflow_versions`.

## 6. Operating Guidelines
- **Versioning**: Always bump `algo_version` (graph extraction) or `workflow_graph.version` when prompts/pipelines change. Agents include these versions in cache keys.
- **Testing**: Graph-aware tests should validate that a query returns the expected entity set, edge types, and workflow plan (snapshot tests + SQL queries).
- **Monitoring**: Track counts of entities/edges per ingestion run, community build success, workflow graph publish events, and GraphRetriever latency.
- **Security**: Graph tables inherit document RLS via `document_id`; cross-document aggregates must only expose aggregated data allowable per user scope.

## 7. Further Reading
- `agent_design.md` – See sections on GraphRAG + WorkflowPlanner nodes.
- `graph_agent_design.md` – Node-level responsibilities and state fields.
- `schema_and_persistence.md` – Detailed schema, indexes, extensions, lifecycle policies.
