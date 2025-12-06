# Task Plan Progress – Task 13: Enforce SQL/Polars for Numeric Reasoning
_Tracker for TASK_PLAN_TASK13_NUMERIC_SQL.md. Keep plan/tracker files after completion per session constraint._

- [x] Step 1: Inspect current numeric pipeline (router, Text→SQL, attachment parsing, citations) and existing tests.
- [x] Step 2: Research numeric extraction + routing cues; finalize schema/heuristics.
- [x] Step 3: Implement LLM numeric fact extractor and integrate into table building with citation preservation.
- [x] Step 4: Update router to force `requires_sql` on numeric cues; adjust SQL fallback if needed.
- [x] Step 5: Extend tests for extractor outputs, router decisions, citation handling/fail-graceful when no rows.
- [x] Step 6: Run quality gates/tests and AWS smoke for numeric prompts; capture evidence/logs.

Notes / evidence:
- Ran targeted tests: `uv run pytest tests/router/test_router_node.py tests/services/test_langgraph_runner.py tests/services/test_numerical_fact_extractor.py`
- Quality gates: `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`
- AWS smoke (AWS mode only): `ENV_FILE=.env.active bash scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_task13.log`
  - Conversation `f8a052a5-5fe3-5e07-8e23-3aaabba75a81`, docs `bbf98ad5-077f-4c00-84fd-4be2f6e19ff1`, `1f538753-185f-4d0b-8360-397bd46ace7a`, `0528e787-47dc-4419-b3a0-e0d60a0309db`
  - `requires_sql` true for ledger/KPI prompts (sum total rental assistance, KPI threshold prompt) per `prod_sample_run.json`
- Deployed to EC2 via `scripts/deploy_ec2_services.sh --host 52.207.140.87 --ssh-key ArchaaS/dist/vizonomy-v2-ec2-dev2.pem`.
- Post-deploy smoke: `ENV_FILE=.env.active bash scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_task13_postdeploy.log` (docs `b8f622e3-abcb-4d7c-a601-868ca4bf50af`, `7f775c98-faff-4490-8b9f-9bc2bcd2596a`, `8b1047c7-fa1e-4bef-8d2d-b47d7bade427`; `requires_sql:true` on ledger/KPI prompts, partial on mixed prompt).
