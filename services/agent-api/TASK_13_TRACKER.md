# Task 13 Tracker – Enforce SQL/Polars for Numeric Reasoning
_Tracker for TASK_13_PLAN.md; keep in place after completion per session constraint._

- [x] Step 1: Inspect router heuristics, table builder/markdown parsing, numerical data flow + tests.
- [x] Step 2: Research numeric extraction + routing cues; finalize schema/heuristics.
- [x] Step 3: Implement LLM fact extractor and integrate synthesized tables with citations.
- [x] Step 4: Update router to auto-set `requires_sql` for numeric cues; adjust fallbacks.
- [x] Step 5: Extend tests for extractor outputs/router decisions/citation + no-row handling.
- [x] Step 6: Run quality gates/tests and AWS numeric smoke; capture evidence.

Notes / evidence:
- Tests: `uv run pytest tests/router/test_router_node.py tests/services/test_langgraph_runner.py tests/services/test_numerical_fact_extractor.py`
- Quality gates: `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`
- AWS smoke (AWS mode): `ENV_FILE=.env.prod bash scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_task13.log`
  - Conversation `f8a052a5-5fe3-5e07-8e23-3aaabba75a81`, docs `bbf98ad5-077f-4c00-84fd-4be2f6e19ff1`, `1f538753-185f-4d0b-8360-397bd46ace7a`, `0528e787-47dc-4419-b3a0-e0d60a0309db`; `requires_sql` true for numeric ledger/KPI prompts in `prod_sample_run.json`
- Deployed to EC2: `scripts/deploy_ec2_services.sh --host 52.207.140.87 --ssh-key ArchaaS/dist/vizonomy-v2-ec2-dev2.pem`.
- Post-deploy smoke: `ENV_FILE=.env.prod bash scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_task13_postdeploy.log` (docs `b8f622e3-abcb-4d7c-a601-868ca4bf50af`, `7f775c98-faff-4490-8b9f-9bc2bcd2596a`, `8b1047c7-fa1e-4bef-8d2d-b47d7bade427`; `requires_sql:true` on ledger/KPI prompts).
