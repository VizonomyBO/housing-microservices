# TASK 05 Tracker

- [x] Step 1: Research FastAPI-friendly reduced-scope email/rate limiter approaches (web/context7) and capture insights in plan. (2025-12-03)
- [x] Step 2: Review existing settings/config + CLI scaffolding for reduced-scope integration. (2025-12-03)
- [ ] Step 3: Implement LoggingEmailProvider module + tests. (blocked pending guidance on missing shared_data_layer auth repositories)
- [ ] Step 4: Implement per-process rate limiter utilities + tests.
- [ ] Step 5: Wire provider + limiter into dependencies/context; emit demo headers.
- [ ] Step 6: Add `/v1/auth/*` public routes and admin override route with repositories + limiter integration.
- [ ] Step 7: Extend CLI helpers for verification toggles + email log inspection (with tests/doc updates).
- [ ] Step 8: Update docs (security, interfaces, README, Docker runbook) + `epic-035/CHECKLIST.md` + Handoff notes.
- [ ] Step 9: Add/extend test coverage for routes/CLI/provider/limiter.
- [ ] Step 10: Run verification suite (ruff format/check, ty check, pytest -n auto) and clean up plan/tracker.
