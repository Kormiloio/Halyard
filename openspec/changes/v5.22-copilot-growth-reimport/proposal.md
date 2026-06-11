# v5.22 — Copilot importer growth re-import

## Why

The Copilot importer freezes every chat session at its first import: the
dedup state (`~/.halyard/copilot-imported`) is a plain id set, so a session
imported while still open never re-imports as it grows. This is the same
defect class already fixed twice — codex in v5.2, the Claude transcript
importer in v5.21 — and it has a live victim: the owner's long-running VS
Code chat session `78930975…` (open since June 5) is frozen at its June 9
23:57 snapshot, so the June 10 continuation will never be captured even
after VS Code flushes it to disk. With chat windows routinely left open for
days (the workflow that motivated the rejected 7-day guard bump in the
June 10 incident), first-import freezing is structural data loss, not an
edge case.

A secondary gap: the frozen row in the ledger was produced by the incident
session's pre-fix parser, so its interaction evidence is suspect
(duplicate-counted response parts).

## What changes

- **State file upgrades to the codex v5.2 format** (`<id>\t<size>` per
  line): an unchanged chat session skips, a grown one re-imports. Legacy
  bare-id lines parse to size-None and re-check once. `record_otel_capture`
  keeps writing ids (sizeless); the authoritative OTel ledger check
  (`_otel_captured_ids`) still backstops them.
- **Imported rows carry `job_id=copilot:<session_id>`** and collapse to one
  canonical row at read time via a new `_copilot_session_key` in
  `ai_log.py` — job-id prefix only, exactly like `_claude_session_key`
  (never `session_id`, which OTel-sourced and legacy rows carry). The
  prefix is distinct from the existing `copilot-otel:` namespace.
- **Ledger-aware coverage** replaces the OTel-only check: a session whose
  id already appears on any `github-copilot` row *not* written by this
  importer (OTel rows, pre-v5.22 import rows, manual rows) is skipped —
  re-importing next to a row that cannot collapse would double-count.
- **One-time refresh of session `78930975…`** (operational): remove the
  pre-fix-parser row and its state entry, re-import with the fixed parser
  so the row regains trustworthy evidence and becomes growth-trackable.

## Out of scope

- Token/cost capture for Copilot chat (the JSONL rarely carries
  `completionTokens`; OTel remains the richer path).
- Growth re-import for the gemini importer (its history file is re-read by
  the live hook every turn; the importer is a backfill for hookless
  machines and its dedup was fixed in v5.21).

## Impact

- Affected: `src/halyard/collectors/copilot.py`, `src/halyard/ai_log.py`,
  new `tests/test_v522_copilot_growth_reimport.py`; docs:
  `collector-coverage.md`, `PRD/ARD-vscode-extension-and-metadata-parity.md`.
- The 30-minute `import-all` timer now keeps long-lived VS Code chat
  sessions current automatically.
