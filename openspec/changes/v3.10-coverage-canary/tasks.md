# Tasks: v3.10 — doctor capture-coverage canary

- [x] `_newest_disk_activity(tool)` probe (claude-code, gemini-cli).
- [x] `_capture_coverage_checks(project_dir, hub_dir)` — disk-vs-ledger lag,
      baseline-gated, grace window, warning-only.
- [x] Wire into `build_doctor_report` (after the drift canary).
- [x] Tests: warns on stale-ledger+fresh-disk; silent on fresh ledger / no
      baseline / within-grace. (`tests/test_v310_coverage_canary.py`)
- [x] ruff + mypy clean; live `halyard doctor` no false positive.
- [x] Roadmap entry (item 64) + CHANGELOG (batched).
