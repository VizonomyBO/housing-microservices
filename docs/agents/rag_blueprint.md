# RAG Blueprint (Revamped Stack)

Guide to the text-only ingestion-first flow and the ReAct agent tool stack. Legacy Lambda/Step Functions/graph/planner content is archived; this blueprint reflects the retained services only.

## Ingestion pipeline
- Entry: `ingestion-service` `POST /v1/documents/upload` returns an HMAC form upload; binary POST goes back to ingestion-service (no S3 Step Functions path).
- Processing: MarkItDown → contextual/proposition chunking → Voyage `voyage-context-3` embeddings (default 1024-d; optional 256/512/2048 when DB matches) → pgvector insert → activation.
- Allowed `source_type`: pdf, docx, doc, txt, md, html, json. Outputs are length-normalized; rerank always runs (`rerank-2.5`).
- Ownership: `owner_id` nullable/“0000” for shared docs; deletes cascade DB + S3 when allowed.

## Retrieval & agent
- **Tools**: hybrid retrieval (BM25 + pgvector) + rerank utility, attachment/status/listing helpers, Pyodide code executor (Wasm sandbox, no filesystem; install extras with `micropip` + `httpx`).
- **Advanced RAG techniques**:
  - HyDE/HyPE expansions when recall is weak.
  - Contextual headers (section/page titles) and proposition-aware chunking.
  - Fusion diversity (avoid single-doc domination), rerank score floors, and filters by country/doc/tags.
  - Citation enforcement: per-fact `[c#]` markers and regeneration when coverage is missing.
- **No fallbacks**: caches, rate limiters, and planner/graph layers are removed. Fail fast on missing dependencies (OpenAI/Voyage/ingestion).

## Prompts & eval guidance
- Keep prompts tool-aware: instruct the model to use retrieval first, then rerank/repair, and call Pyodide only for deterministic calculations.
- Include contextual headers and chunk IDs in the prompt to ground citations.
- Enforce structured outputs when numeric/table reasoning is required; otherwise prefer concise prose with inline `[c#]` markers.
- Evals should hit real services (no stubs) and measure faithfulness/context recall. Use the same retrieval path as production; do not bypass tools.

## Environments
- Local dev: `docker compose --env-file "$env_file" up -d --build` (LocalStack required) → `./test-api.sh`.
- Hybrid dev: `docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service`.
- Prod: `scripts/deploy_stack.sh --mode services-only|full-redeploy`; smoke with `scripts/prod_smoke_check.sh` (upload → activate → attach → chat).
