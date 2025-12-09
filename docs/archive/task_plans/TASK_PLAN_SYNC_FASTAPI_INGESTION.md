# Task Plan – FastAPI-Based Synchronous Ingestion Replacement
_Plan auto-approved per AGENTS.md; tracker will mirror progress. Do not delete per user directive._

## Request Summary
Replace the broken Lambda/S3 ingestion path with a simple FastAPI service (own `uv` venv) running on EC2. The service should expose an upload endpoint compatible with the existing ingestion API, synchronously process PDFs with MarkItDown (chunk, embed, index, activate), and be wired so other services treat it like the previous Lambda-triggered flow. Deploy to the existing EC2 host alongside other services; keep it minimal (no Redis/workers).

## Impacted Files/Areas
- New FastAPI ingestion service (likely under `services/`), docker/venv config, compose/EC2 deploy scripts.
- Agent-api ingestion client/wiring + smoke scripts (`scripts/prod_smoke_check.sh`, runbooks).
- Task docs (`TASK_DEFINITION.md`, `TASK_PLAN.md`, `TASK_PLAN_PROGRESS.md`, `task_prompts/14_sync_fastapi_ingestion.md` etc.) to insert the new task and shift numbering.
- README and endpoint references/runbooks.

## Risks / Unknowns
- Parity with existing payload/response semantics (content hash dedupe, status fields, activation sequence).
- Resource contention on EC2 (CPU/memory for synchronous PDF processing).
- Keeping the interface identical so other services don’t need major rewrites.
- Deployment idempotence and env sourcing with the existing `.env` / `scripts/use_env.sh`.

## Ordered Steps (all completed)
1. Read new prompt `task_prompts/14_sync_fastapi_ingestion.md` and existing plan/tracker rows (13–15) to understand dependencies and numbering changes.
2. Research FastAPI + MarkItDown sync ingestion best practices (Serper/Context7) and note sources here.
3. Update task docs/plans to insert the new task and shift subsequent tasks; create/update tracker for this plan.
4. Design the FastAPI ingestion service (venv/uv, endpoints matching Lambda API contract, sync pipeline with markitdown → chunk → embed → index → activate).
5. Wire agent-api and smoke scripts to target the new service; adjust runbooks and endpoint references.
6. Add deploy automation to run the new service on EC2 alongside existing compose/services (idempotent entrypoint).
7. Verify end-to-end ingestion via curl/smoke against AWS; capture evidence; update tracker/docs.

## Research Sources
- FastAPI file uploads (`UploadFile`, form data) official docs: <https://fastapi.tiangolo.com/tutorial/request-files/>
- FastAPI background task guidance and when to avoid it for critical work: <https://fastapi.tiangolo.com/tutorial/background-tasks/>
- Uvicorn/Gunicorn timeout tuning for long-running requests (StackOverflow + Gunicorn examples): <https://stackoverflow.com/questions/63961160/fastapi-workers-timeout>, <https://medium.com/@iklobato/mastering-gunicorn-and-uvicorn-the-right-way-to-deploy-fastapi-applications-aaa06849841e>
- MarkItDown usage and conversion examples (GitHub + RealPython guide): <https://github.com/microsoft/markitdown>, <https://realpython.com/python-markitdown/>
