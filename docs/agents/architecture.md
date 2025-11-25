# Graph Agent Design for RAG and Agentic Platform
Version: 1.0

1. Purpose and Scope
- This document specifies the design and implementation components of the LangGraph-based agent described in [system_architecture.md](../overview/system_architecture.md). It defines node responsibilities, state, edges, routing conditions, loops, parallelism, persistence, and nonfunctional concerns. No code is included; this is an implementation blueprint.

2. Architectural Constraints derived from system_architecture.md
- Orchestration: LangGraph for explicit control, deterministic loops, branching, retries, and state with durable execution and human-in-the-loop.
- Retrieval backends: PostgreSQL + pgvector with hybrid search (vector + tsquery + metadata filtering).
- Embeddings and reranking: Voyage AI (embeddings: voyage-3.5-lite; reranker: rerank-2.5-lite).
- Subgraphs: Informational RAG; Analyst/Proposer; Numerical (Text-to-Polars-SQL + Calculator); Vision.
- Graph reasoning: GraphRAG + workflow graphs augment retrieval outputs before subgraph routing.
- Centralized rate limiting via Valkey-based token buckets with priority lanes and token-aware estimation.
- Deterministic cache keys for replayability and cost reduction.
- Pillar Answer Engine uses identical chain as interactive to ensure determinism.

3. High-Level Graph Overview
- Single router graph with specialized subgraphs. Core phases:
  1) Input normalization and session hydration
  2) Routing to a subgraph
  3) Retrieval orchestration (parallel hybrid retrieval -> fusion -> rerank)
  4) Subgraph-specific reasoning and tool use
  5) Answer synthesis with citations and guardrails
  6) Persistence, caching, and telemetry
- The graph is resilient: retries, backoffs, loop limits, and optional human interrupts.

4. State Model (authoritative contract across nodes)
Represented as a typed key-value state that evolves monotonically. Key categories:
- Conversation and context
  - messages: ordered list of user/assistant/tool messages
  - conversation_id, thread_id: identifiers for checkpointing and resume
  - country_code: inferred or provided, drives policy and document scope
  - doc_version_ids: set of document versions in scope
- Routing and control
  - route: one of {informational, analyst, numerical, vision}
  - route_confidence: float [0,1]; thresholds drive escalations
  - loop_counters: per-loop maps (retrieval_attempts, tool_retries, answer_refinements)
  - interrupts: latest human interrupt payload, if any
  - timing: start_time, deadlines, timeouts per phase
- Retrieval artifacts
  - raw_candidates: channel->list of raw results with scores and provenance
  - fused_candidates: list after RRF fusion with fused scores
  - reranked_candidates: list after Voyage rerank with relevance scores
  - final_context: capped list of selected items for answer synthesis
  - retrieval_metrics: per-channel latencies, counts, probes, distance thresholds
- Tool results
  - sql_query: generated Polars SQL plan for the selected table(s)
  - sql_validation: results of static checks vs schema_summary
  - sql_result: output rows/values from Polars SQL execution
  - calculator_inputs, calculator_result: numbers and computed values
  - vision_inputs, vision_result: figure references, captions, analysis summaries
- Graph reasoning
  - graph_context: entity clusters, relationship summaries, freshness indicators
  - workflow_plan: ordered steps sourced from workflow graphs (coarse/mid/fine granularity)
- Answering and citations
  - draft_answer: text produced prior to verification
  - citations: list of {doc_id, chunk_id, page_num, offsets, evidence_text, score}
  - answer: final answer text
  - quality: confidence score, groundedness score, hallucination risk estimate
- Caching and limits
  - cache_key: deterministic key per 4.3
  - cache_hits: booleans and payload pointers
  - rate_limiter_permits: acquired permit records
  - error: latest error classification, for retries and fallbacks

5. Node Inventory and Responsibilities

5.1 InputNormalizer
- Purpose: Normalize user input, extract explicit selectors (country, doc hints, task type), sanitize prompt, and populate initial state. Computes deterministic cache_key inputs.
- Inputs: user message, optional metadata.
- Outputs: normalized prompt, country_code, initial route hints, cache_key preimage.
- Edge conditions:
  - If cache hit for cache_key: jump to CacheReturn
  - Else: proceed to SessionLoader

5.2 SessionLoader
- Purpose: Hydrate prior messages and any persisted plan/context via thread_id or conversation_id. Enforce TTL and redact sensitive content per policy.
- Outputs: messages augmented with history, doc_version_ids if pinned to user session.
- Errors: if missing conversation, start fresh; no fatal error.
- Edge: proceed to Router

5.3 Router
- Purpose: Classify intent into {informational, analyst, numerical, vision}. Optionally suggest query expansion mode {none, hyde, hype}.
- Signals considered: prompt features, keywords (e.g., “calculate”, “table”), presence of figure/table refs, prior loop outcomes, country constraints.
- Outputs: route, route_confidence, expansion_mode.
- Edge conditions:
  - If confidence < min_route_conf: escalate to HumanGate or fallback to informational
  - Else route to the selected subgraph entry.

5.4 Retrieval Orchestrator Subgraph
Composed of the following nodes:
- QueryExpander (optional):
  - Purpose: Generate semantic expansions only if retrieval quality previously failed or when expansion_mode != none.
  - Outputs: augmented queries (hyde/hype variants), constrained by token budget.
  - Edge: to ParallelRetrievers
- ParallelRetrievers:
  - Purpose: Execute four channels concurrently:
    - Text Retriever (pgvector ANN index on text chunks)
    - Table Retriever (pgvector on table captions/schema summaries)
    - Image Caption Retriever (pgvector on figure captions)
    - Keyword Search (GIN tsquery on text_tsv)
  - Design:
    - Use LangGraph parallel edges or Send to fan-out; each branch writes channel-specific raw_candidates with distances and filters.
    - Apply metadata filters (country_code, doc_id, version).
    - Tune pgvector index usage:
      - IVFFlat or HNSW operator class per distance metric; set probes/ef_search per query complexity and enable iterative_scan for filtered queries to improve recall.
  - Edge: to Fusion
- Fusion (RRF):
  - Purpose: Merge multi-channel results using Reciprocal Rank Fusion:
    - fused_score(d) = sum_over_channels(1 / (k + rank_d_channel))
    - k is a small constant (e.g., 60) to smooth long tails.
  - Outputs: fused_candidates ordered by fused_score.
  - Edge: to Reranker
- Reranker (Voyage AI):
  - Purpose: Contextual reranking with Voyage rerank-2.5-lite using user query (or expanded query) and candidate texts.
  - Constraints: obey model token and documents limits; use truncation if enabled; optionally set top_k.
  - Outputs: reranked_candidates with relevance scores; final_context selected (top K with score floor).
  - Edge conditions:
    - If insufficient quality (e.g., top score < min_rerank_score or fewer than min_k): back to QueryExpander (max N loops), else proceed.
- GraphRAG + Workflow Graph Layer:
  - GraphRetriever queries the long-lived knowledge graph (entities, relationships, community clusters) seeded during ingestion and refreshed on document updates. Inputs include the normalized query, reranked hits, and document scope filters.
  - GraphSummarizer compacts returned neighborhoods into `graph_context` payloads (per-entity evidence summaries, freshness metadata, cross-document links) that downstream subgraphs can cite deterministically.
  - WorkflowPlanner takes the query intent plus graph context and projects it onto a workflow graph catalog that encodes coarse/mid/fine troubleshooting steps. The resulting `workflow_plan` lists prescribed actions, preconditions, and associated tools, ready for Analyst/Numerical subgraphs or HITL review.

5.5 Subgraphs

A) Informational RAG Subgraph
- Purpose: Grounded Q&A with strict citations.
- Flow:
  - Ensure final_context is populated; if not, run Retrieval Orchestrator.
  - AnswerSynthesizer:
    - Compose a concise answer with inline citation markers referencing chunk/page IDs.
    - Enforce policy: no claims without citations; avoid speculation; include country scoping.
  - CitationVerifier:
    - Validate every citation spans the claimed facts; cross-check evidence_text contains the asserted numbers/names.
    - If any fail, route back to Retrieval Orchestrator with adjusted constraints or increased k, else continue.
  - Guardrails:
    - Redact PII if policy triggers; enforce style guide; attach a confidence estimate and list of sources.
- Exit: answer, citations, quality.

B) Analyst/Proposer Subgraph
- Purpose: Synthesize across documents; produce comparisons, options, or recommendations grounded in evidence.
- Flow:
  - If context insufficiently diverse (few distinct doc_ids), loop retrieval to diversify candidates (use diversity constraints at fusion).
  - Plan-and-Synthesize:
    - Generate a brief outline of comparative criteria tied to retrieved evidence anchors.
    - For each criterion, source snippets and cite them.
  - Risk and Tradeoff Pass:
    - Add caveats; constraints by country_code; explicit unknowns.
  - Verification Loop:
    - CitationVerifier on each comparative claim; if fails, re-fetch targeted evidence.
- Exit: structured comparative answer with per-claim citations.

C) Numerical Subgraph
- Purpose: Quantitative analysis over structured table artifacts using Polars SQL with strict validation.
- Flow:
  - Table Selector:
    - From reranked_candidates/graph_context, select target table JSONs based on schema_summary similarity, graph edges (e.g., `Impacts`, `Contains_Metric`), and relevance to user query.
  - Text-to-Polars-SQL Planner:
    - Translate NL question to a constrained Polars SQL query that references only registered tables/columns.
    - Grounding constraints: enforce schema-derived column lists, forbid DML, limit arithmetic/logical functions to an allowlist.
  - Static Validator:
    - Parse the query via `pl.SQLContext().parse()` (or dry-run) to confirm identifiers and types, logging failures into `sql_validation`.
  - Polars SQL Executor:
    - Register the selected table(s) via `SQLContext.register(name, LazyFrame)` and call `ctx.execute(query, eager=True)` so execution occurs in-memory with time/memory caps.
    - If empty or ambiguous, prompt a clarification interrupt or retry with relaxed selection (e.g., include additional tables).
  - Calculator:
    - Apply precise arithmetic for follow-up computations (growth rates, deltas) while echoing the formulas in the final answer.
  - NumericalSynthesizer:
    - Produce a step-by-step derivation with citations to table sources, row coordinates, and workflow-plan steps (e.g., “Step 2: Validate fiscal totals”).
- Exit: numeric result(s) + derivation + citations.

D) Vision Subgraph
- Purpose: Retrieve and analyze figures/images with optional escalation to higher-detail vision model.
- Flow:
  - Figure Selector from reranked figure candidates; fetch low-detail caption first.
  - VisionTool:
    - Run low-detail analysis unless confidence < threshold, then escalate to higher-detail model.
  - VisionSynthesizer:
    - Provide a grounded description; link to figure id/page; include caution for non-textual inference.
- Exit: visual analysis summary + citations.

5.6 CacheReturn
- Purpose: On cache hit, return prior answer with provenance to ensure idempotence and cost savings.
- Edge: to Exit

5.7 Guardrails and Policy Node (shared)
- Purpose: Apply content policies, PII redaction, formatting normalization, and jurisdictional constraints based on country_code.
- Inputs: answer, citations, quality
- Outputs: policy_compliant_answer; logs of any redactions.

5.8 ErrorHandler/Retry
- Purpose: Centralize retry policies:
  - Classify errors into transient (rate limit, 5xx) vs permanent (validation, missing artifact).
  - Apply exponential backoff governed by centralized limiter hints; cap retries per node.
  - On persistent failure, produce a safe fallback (apology + how to proceed) with partial citations if available.

5.9 RateLimiter Node
- Purpose: Acquire token permits for LLM calls with lane priorities (interactive > batch), using token estimates and OpenAI-like headers for backoff calculation.
- Edge: gating edge before LLM-bound nodes (Router LLM, QueryExpander, AnswerSynthesizer, VisionTool).

6. Edges and Movement Conditions

6.1 Entry and Early Exit
- START -> InputNormalizer
- If cache hit -> CacheReturn -> END

6.2 Routing
- SessionLoader -> Router
- Router:
  - If route_confidence < threshold_low: Router -> HumanGate (interrupt); after resume, re-enter Router
  - Else Router -> {Informational, Analyst, Numerical, Vision} subgraph entry

6.3 Retrieval Loops
- Subgraph entry -> Retrieval Orchestrator (if final_context missing or stale)
- Retrieval loop conditions:
  - If fused top score below min_fused_score OR reranked top score < min_rerank_score:
    - If expansion_used < max_expansions: go to QueryExpander
    - Else if keyword_only_attempted is false: disable vector channels and try tsquery-only
    - Else if widen_filters_possible: relax country/doc filters one step, then retry
    - Else: break with low-confidence flag and proceed to conservative answer template

6.4 Tool Branching
- In subgraphs that include tool usage, apply tools_condition-like branching:
  - If LLM plans a tool call, route to tool node; upon completion, return to the planning node
  - Constrain to at most one outstanding tool call per loop to maintain determinism

6.5 Verification and Repair
- After AnswerSynthesizer -> CitationVerifier
  - If any citation fails match or coverage thresholds: route back to Retrieval Orchestrator with targeted query augmentation and increment repair counter
  - Stop when repair counter >= max_repairs, then degrade gracefully with explicit uncertainty

6.6 Human-in-the-Loop
- Any node can raise an interrupt (e.g., need clarification, disambiguation among tables)
- On resume, the graph continues from the interrupted node with injected human input; subgraphs must be idempotent where possible

6.7 Timeouts and Deadlines
- Each node observes per-phase deadlines; on timeout, route to ErrorHandler/Retry
- Global deadline preempts loops and forces summary with best-effort citations

7. Parallelism and Concurrency Model
- Retrieval channels execute in parallel branches; use Send or multi-edge fan-out, with a join at Fusion.
- Within a single user thread_id, enforce sequential node execution per LangGraph’s semantics; concurrent user sessions are independent.
- Configure concurrency ceilings per tool class to respect external rate limits; the RateLimiter gates before LLM nodes.

8. Persistence, Checkpointing, and Threads
- Use a checkpointer to persist state at node boundaries; thread_id is stable through a conversation.
- Interrupts require a checkpointer; the system stores __interrupt__ envelopes and resumes with Command-like semantics.
- Persist artifacts:
  - reranked_candidates and final_context to enable cache hits and deterministic replay
  - answer, citations, token usage, and tool call traces for audit and analytics

9. Observability and Provenance
- Tracing: instrument each node with spans including inputs (sizes/hashes), outputs (sizes/hashes), latency, and retry counts.
- LangSmith or equivalent: visualize graph trajectory with node-level state snapshots.
- Provenance model:
  - citations reference document id, chunk id, page number, and byte/char offsets
  - store the exact prompts and tool parameters used for reproducibility
- Metrics:
  - retrieval precision@k, coverage, rerank uplift
  - loop counts, expansion rates, cache hit ratio
  - rate limit waits, token consumption

10. Security and Safety
- Secrets: stored in AWS Secrets Manager, retrieved via IAM roles at runtime; never persisted in state.
- Data access: SQL queries parameterized; S3 access via presigned URLs; no raw keys in memory longer than necessary.
- Tool sandboxing:
- Text-to-Polars-SQL: enforce schema-derived column allowlists, forbid DML/functions outside a curated set, and cap execution time/memory inside the Polars engine.
  - Calculator: deterministic, pure numeric evaluation; disallow eval, arbitrary code.
  - Vision: strip EXIF and sensitive metadata; avoid image exfiltration.
- Prompt injection guardrails:
  - System prompts reinforce citation requirements and ignore external instructions
  - Never execute tool commands suggested by untrusted content without validation
- PII and policy:
  - Apply country-specific redactions; audit logs for any redaction applied.

11. Configuration and Tunables (defaults reference)
- Models:
  - Chat/analysis: GPT-5-mini
  - Embeddings: voyage-3.5-lite
  - Reranker: rerank-2.5-lite
  - Vision: low detail for captioning; mini for analysis
- Retrieval:
  - hybrid_k: 10 after fusion+rerank
  - pgvector index: IVFFlat vs HNSW chosen per table volume; tune lists/probes or ef_search; iterative_scan for filtered queries
  - RRF: k parameter (e.g., 60), per-channel weights optional
- Loops and thresholds:
  - max_retrieval_loops: 2
  - min_fused_score: tuned empirically
  - min_rerank_score: tuned empirically
  - max_repairs: 1
  - tool_retries: 2
- Cache TTL: 48–72h
- Rate limiting:
  - token bucket capacities and lane weights; backoff windows derived from provider headers

12. Deployment and Scaling Considerations
- EC2 hosts the always-on agent and API; Lambdas handle ingestion and asynchronous jobs.
- Ensure LangGraph runtime state is externalized via checkpointer so processes can be restarted without losing progress.
- Set conservative parallelism defaults to avoid overloading Voyage AI and the database; scale read replicas or connection pooling as needed.
- Use PgBouncer for connection pooling; monitor index health and vacuum.

13. Subgraph Design Details

13.1 Informational RAG
- Entry criteria: route=informational or fallback; context missing or stale triggers retrieval.
- Answer policy: every sentence that asserts a fact must have an adjacent citation marker; unknown is acceptable and preferred over speculation.
- Movement:
  - If quality < threshold after verification, escalate to Analyst/Proposer for synthesis if the query implies comparison, else return conservative answer.

13.2 Analyst/Proposer
- Entry criteria: route=analyst or informational upgrade; query implies comparison/recommendation.
- Movement:
  - If insufficient distinct sources, loop retrieval with diversity constraints.
  - If numeric claims emerge, delegate leaf calculations to Numerical subgraph, then continue synthesis.

13.3 Numerical
- Entry criteria: route=numerical or analyst requiring quantification.
- Movement:
  - On validation failure, request clarification via interrupt specifying required column/row disambiguation.
  - If jq_result empty, attempt alternate table candidate, else fall back to textual extraction with explicit uncertainty.

13.4 Vision
- Entry criteria: route=vision or informational with figure focus.
- Movement:
  - If confidence low after low-detail pass, escalate; if still low, request human clarification (e.g., specify figure id).

14. Data Access Patterns for Hybrid Retrieval (pgvector)
- Vector search:
  - Choose operator class per model normalization: cosine for normalized embeddings; inner product for OpenAI-like; l2 alternative.
  - IVFFlat tuning: lists sized by rows; probes near sqrt(lists) baseline; use LOCAL settings per query.
  - HNSW tuning: ef_search tuned per latency/recall; iterative_scan for filtered queries.
- Hybrid:
  - Combine vector results with tsquery exact matches; feed into RRF before rerank.
  - Apply metadata filters early (country_code, doc_id, version) to reduce candidate pools.
- Post-retrieval rerank:
  - Respect Voyage reranker docs: pass top N candidates, obey token limits and top_k; enable truncation to avoid errors.

15. Citation Data Model
- citation:
  - doc_id: uuid
  - chunk_id: uuid
  - page_num: int
  - offsets: start,end positions or bounding box for tables
  - evidence_text: short excerpt
  - score: relevance/confidence
- Rules: one citation per atomic claim or per sentence; for numeric derivations, cite the raw source rows.

16. Deterministic Cache Key Composition
- Per [system_architecture.md Section 4.3](../overview/system_architecture.md#43-cache-key-generation); incorporate:
  - country_code
  - normalized_prompt
  - sorted document version ids
  - agent route
  - expansion_mode
  - tool parameters (jq hash, calc inputs)
  - retrieval parameters (k, thresholds)
- Movement:
  - Cache check after InputNormalizer and prior to expensive calls; write-through after finalization.

17. Failure Modes and Fallbacks
- Voyage rate limits: backoff via headers, reduce parallelism, shrink candidate counts, or increase truncation.
- Database overload: degrade to tsquery-only or smaller k; delay via limiter.
- Reranker errors: bypass rerank and rely on fused RRF with stricter citation verification.
- Tool validation failures: present natural-language request for human clarification.
- Vision failures: provide caption-only with uncertainty.

18. Testing and Evaluation Plan
- Offline evals:
  - Retrieval: recall@k, nDCG with human-labeled relevance
  - Rerank uplift: compare fused vs reranked top-k quality
  - Numerical: program synthesis accuracy and execution correctness on gold tables
  - Citation correctness: coverage and precision audits
- Online guardrails:
  - No-answer rate where warranted; hallucination audits
  - Time to first token and total latency SLOs

19. Implementation Notes aligned with LangGraph capabilities
- Use conditional edges for routing; add parallel branches for retrievers; use Send for dynamic fan-out if needed.
- Enable checkpointer for HIL interrupts and durable execution.
- Use a ToolNode-like pattern for tool dispatch with a strict tools_condition function to prevent uncontrolled tool loops.
- Ensure idempotence for nodes that may re-run after interrupts (e.g., parent nodes vs subgraph nodes).

20. Summary of Edges (non-exhaustive)
- START -> InputNormalizer
- InputNormalizer -> (CacheReturn | SessionLoader)
- SessionLoader -> Router
- Router -> Informational | Analyst | Numerical | Vision | HumanGate
- Subgraph Entry -> (Retrieval Orchestrator if needed) -> Fusion -> Reranker
- Reranker -> (QueryExpander | Subgraph Planner)
- Subgraph Planner -> (Tool Nodes as needed) -> AnswerSynthesizer
- AnswerSynthesizer -> CitationVerifier -> (Repair | Guardrails)
- Guardrails -> CacheWriter -> END
- ErrorHandler/Retry reachable from any node on failure; may return to node of origin or exit with safe fallback.

21. Configuration Table (indicative)
- Route thresholds:
  - route_confidence: 0.55 low, 0.75 high
- Retrieval:
  - hybrid_k: 10, candidates_before_rerank: 50–200 depending on token budget
  - RRF k: 60
- Rerank:
  - model: rerank-2.5-lite
  - top_k: 32 default, tuned
- Numerical:
  - jq allowlist: identity, ., [], |, map, select, reduce, add, length, keys, to_entries, from_entries, arithmetic ops
  - execution limits: 250 ms CPU, 32 MB memory
- Vision:
  - escalate if confidence < 0.6
- Loops:
  - max_retrieval_loops: 2; max_repairs: 1

22. Open Questions and Future Enhancements
- Adaptive per-country retrieval filters learned from feedback
- Learned fusion weights per channel
- Active learning for Text-to-Polars-SQL translation with user corrections
- Advanced table alignment across document versions for trend analysis

References consulted
- LangGraph core concepts: state, nodes, edges, conditional edges, subgraphs, parallel branches, interrupts, checkpoints, Send API, durable execution, and ToolNode patterns.
- pgvector indexing and query tuning: IVFFlat vs HNSW, operator classes, probes/ef_search, iterative_scan, and hybrid SQL patterns.
- Voyage AI APIs: embeddings (voyage-3.5-lite) and reranker (rerank-2.5-lite) endpoints, limits, truncation, top_k usage, batching, and rate limits.
- jq/gojq semantics for safe table querying and static validation principles.
