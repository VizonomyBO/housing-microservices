# Task Tracker – Restore real eval/smoke dependencies
- Plan auto-approved; updating progress here. Root task files untouched.

## Steps
- [x] Capture current stub usage and failure points.
- [x] Remove eval/smoke stubs; wire eval tests to real runner/metric engine.
- [x] Load `.env.prod` for evals; force real stack and secrets.
- [ ] Confirm Graph/Valkey/rate-limit dependencies satisfied without fallbacks.
- [ ] Run quality gates (ruff format/check, ty, pytest) as feasible; verify.
- [ ] Remove this tracker + plan after completion.
