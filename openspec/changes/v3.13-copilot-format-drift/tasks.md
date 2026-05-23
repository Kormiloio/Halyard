# Tasks: v3.13 — Copilot format-drift fix + importer coverage canary

- [x] Rewrite `parse_chat_session` to reconstruct the incremental patch format
      (`kind:0` snapshot + `kind:1/2` key-path updates via `_apply_patch`),
      then count from the final state. Metadata only.
- [x] Regression test: `["requests", N, "response"]` sub-path format imports
      (not skipped); content never reaches the log line.
- [x] Existing copilot tests still pass (whole-array + no-`kind:0` privacy case).
- [x] Extend v3.10 canary `_capture_coverage_checks` / `_newest_disk_activity`
      to `github-copilot` + `codex`; per-tool fix strings.
- [x] Test: stale importer tool (disk newer than last import) → warning.
- [x] Re-imported the live 2026-05-23 review into the ledger (Copilot 13→14).
- [x] ruff + mypy + full suite green.
- [x] Roadmap entry (item 66) + CHANGELOG.
