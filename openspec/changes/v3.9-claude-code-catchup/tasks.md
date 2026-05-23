# Tasks: v3.9 — Claude Code Stop-hook catch-up

- [x] Add `_last_recorded_end(project_dir, session_id)` watermark helper.
- [x] `handle_stop_hook` anchors transcript read to the watermark when prior
      rows exist for the session.
- [x] Regression tests: catch-up recovers a missed-turn gap; first-turn
      (no prior row) unchanged. (`tests/test_v39_claude_code_catchup.py`)
- [x] ruff + mypy clean; Claude Code collector suites green.
- [x] Roadmap entry (item 63) + CHANGELOG.
- [ ] Note: the live fix only helps once the installed hook binary is
      upgraded (`~/.local/share/uv/tools/halyard`), not the dev venv.
