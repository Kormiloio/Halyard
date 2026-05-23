# Proposal: v3.13 — Copilot session format-drift fix + importer coverage canary

## Why this exists

A live test (2026-05-23) ran a Copilot code review in VS Code; `halyard
import-copilot` captured **nothing**. Diagnosis: not a path/glob bug (the
importer already reads the current `workspaceStorage/<ws>/chatSessions/`
location) — VS Code changed the **session file format**. It is now an
incremental patch log: a `kind:0` snapshot followed by `kind:1` (scalar) and
`kind:2` (value) events that each set a value at a nested key path `k`. The
model output now arrives via `["requests", N, "response"]` **sub-path** updates;
the old parser only applied a whole-array `["requests"]` replace, so it never
saw the response, counted zero work, and skipped every recent session as
"empty".

This is the same format-drift class as the Gemini outage. v3.10's coverage
canary did not catch it because it only probed the live-capture tools
(`claude-code`, `gemini-cli`), not importer tools.

## What changes

- **`copilot.parse_chat_session` rewritten** to reconstruct the final session
  state by applying the `kind:0` snapshot + `kind:1/2` key-path patches, then
  count interactions/tools/tokens from the reconstructed `requests`. Handles
  both the new sub-path form and the legacy whole-array form (and a file that
  starts mid-stream with no `kind:0`). Still metadata-only — message/response
  content is never read (privacy test retained + strengthened).
- **v3.10 coverage canary extended** to `github-copilot` and `codex`: an
  on-disk session newer than the last captured row (beyond the grace) now warns
  that the importer is failing — so a future Copilot/Codex silent break is
  flagged instead of going unnoticed.

## Scope

- Bug-class fix + a monitoring extension (spec-exempt per CLAUDE.md, documented
  here for the record because it's part of the capture-integrity arc).
- This **restores capture today**; the durable fix for the recurring
  format-drift cycle is the OTel ingestion path specced in v3.12.

## Success criteria

- A real current-format Copilot session imports (verified: the 2026-05-23
  review captured — 779 output tokens, 5 assistant parts).
- Regression test covers the `["requests", N, "response"]` sub-path format.
- `doctor` warns when a Copilot/Codex on-disk session is newer than the last
  import. ruff/mypy/full-suite green.
