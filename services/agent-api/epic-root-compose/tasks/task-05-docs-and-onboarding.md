# Task 05 — Documentation & Developer Workflow Update

## System Snapshot
- The new Compose stack, env templates, and LocalStack toggle are in place (Tasks 02–04).
- README/QUICKSTART/docs still describe the old per-service Compose flows (e.g., `services/agent-api/docker-compose.reduced.yml`) and do not mention the LocalStack flag or stack profiles.
- New contributors lack a single runbook that explains how to copy `.env`, launch reduced vs full profiles, seed sample data, and verify the stack.

## Goal
Refresh the top-level documentation so that a developer can clone the repo, copy `.env.example`, run `docker compose up`, and interact with the platform (either reduced or full mode) without reading outdated instructions. Documentation should also explain how to switch LocalStack on/off, how to run smoke tests, and how to troubleshoot common issues.

## Must Read / Inspect Before Coding
1. Updated artifacts from Tasks 02–04: `docker-compose.yml`, `.env.example`, `docs/infrastructure/root_compose_plan.md`.
2. Existing documents: `README.md`, `QUICKSTART.md`, `docs/infrastructure/infrastructure_and_deployment.md`, `docs/runbooks/reduced_scope_demo.md`, plus any service-specific READMEs referencing old Compose flows.
3. Scripts referenced by the new stack (e.g., `services/agent-api/scripts/seed_reduced_scope_data.py`, `scripts/verify_reduced_scope_compose.sh`).

## Implementation Scope & Files
- Update `README.md` (and `QUICKSTART.md` if redundancy is helpful) to include:
  - Prerequisites (Docker, Docker Compose v2, env file setup).
  - Step-by-step instructions for `cp .env.example .env`, editing secrets, and choosing stack profile (`STACK_PROFILE` or `--profile reduced/full`).
  - Commands to launch the stack (`docker compose up --build`, optional profile flags).
  - Instructions for seeding data, verifying health endpoints, and accessing each service’s port.
  - Explanation of the LocalStack toggle (`USE_LOCALSTACK`) and how to switch to real AWS services.
  - Basic troubleshooting tips (e.g., clearing volumes, re-running migrations/seeds).
- Update any remaining docs referencing `services/agent-api/docker-compose.reduced.yml` to point to the new root workflow.
- If helpful, add a new runbook under `docs/runbooks/` describing “Full Stack Local Development” that complements the existing Reduced Scope runbook.
- Ensure `RUN_TASKS.md` or other automation references use the new Compose instructions when relevant.

## Step-by-Step Instructions
1. **Audit documentation**:
   - Search for `docker-compose.reduced`, `services/agent-api/docker-compose`, or other outdated commands.
   - List each document that needs edits.
2. **Update README/QUICKSTART**:
   - Add concise sections: “Prerequisites”, “Setup (.env)”, “Running Reduced Profile”, “Running Full Profile”, “LocalStack vs AWS”, “Stopping & Cleaning Up”.
   - Include code blocks for key commands (e.g., `docker compose --profile reduced up --build`).
3. **Add/Update runbooks**:
   - If the existing `docs/runbooks/reduced_scope_demo.md` is still relevant, link to it; otherwise, create/expand a runbook covering the new root stack (`docs/runbooks/full_stack_compose.md` or similar).
4. **Cross-check references**:
   - Ensure other docs (deployment, scripts, READMEs under `services/`) reference the new Compose flow.
5. **Verification**:
   - Run `docker compose --profile reduced up -d` (optional but recommended) to validate instructions.
   - Run `docker compose --profile full config` to confirm docs match reality.
6. **Polish**:
   - Proofread for clarity, add any diagrams or tables if they aid understanding.
   - Update `services/agent-api/epic-root-compose/CHECKLIST.md` to mark Task 05 complete.

## Definition of Done
- `README.md` (and other impacted docs) clearly describe how to run the stack via the new root Compose, including env setup, profiles, and LocalStack usage.
- No documentation references the removed `services/agent-api/docker-compose.reduced.yml`.
- Developers following the README steps can bring up the stack without guessing missing env vars or flags.
- Optional runbooks are updated/created as needed.
- Task 05 logs include any verification commands run (`docker compose`, smoke scripts, etc.).

## Handoff Notes
- Docs were updated on 2025-12-03 to describe the root Compose workflow, LocalStack toggle, and new runbooks. Future agents should extend the same sections if additional services/profiles are added.
- If upcoming tasks introduce new verification scripts or CLI helpers, remember to cross-link them from `README.md`, `QUICKSTART.md`, and the runbooks so onboarding stays single-sourced.
- The next doc-focused effort should validate whether automation (Make targets, GitHub Actions docs) also needs references to the new compose profiles; no action was required in Task 05 because those files already referenced root compose.
