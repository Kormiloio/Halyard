# Tasks: v3.11 — import-all + scheduled importer

- [x] Extract `run_gemini_import(*, dry_run, all_projects, quiet)` shared by
      `import-gemini` and `import-all`.
- [x] `halyard import-all` — Codex + Copilot + Gemini, idempotent, per-tool
      counts.
- [x] `import_timer.py` LaunchAgent (`StartInterval`, XML-escaped, absolute
      exe) + `install-import-timer` / `uninstall-import-timer` (macOS-guarded).
- [x] Tests: plist runs `import-all` on interval; path escaping valid XML.
      (`tests/test_v311_import_timer.py`)
- [x] ruff + format + mypy clean; commands registered in `--help`.
- [x] Fix cwd-dependent dedup in `run_gemini_import` (`_existing_gemini_ids`
      per target dir) + regression test — the launchd job re-imported on every
      run otherwise.
- [x] Enabled the timer (loaded via launchctl); verified RunAtLoad first run is
      a clean no-op (no duplicates). Required `uv tool install --reinstall
      --no-cache .` (force-rebuild) so the installed binary has the fix.
- [x] Cleaned duplicate job_id rows created while diagnosing (all logs, backups).

## Verification / VS Code (parent investigation)

- [x] Confirmed Codex + Copilot importers are already up to date (no new
      sessions) — recent VS Code + Copilot chat work is captured.
- [x] Root-caused the Halyard VS Code extension capturing once: default
      `halyard.executable: "halyard"` isn't on a Finder-launched VS Code's
      PATH. Set absolute `~/.local/bin/halyard` in user VS Code settings
      (backup written).
- [ ] Follow-up: extension should resolve halyard's absolute path itself
      (PATH-independent) — vscode-extension code change, tracked separately.
- [ ] Not done by design: enabling the live timer (autonomous writer — opt-in).
