# v5.2 — Codex importer: re-import in-progress sessions

## Why

The Codex importer marks a session's UUID as "imported" the first time it sees
the rollout file, then skips that UUID forever
(`collectors/codex_app.py`: `if session_id in already_imported: continue`).

When the scheduled importer runs while a Codex session is still being written,
it captures only the partial snapshot that exists at that moment and freezes it.
Observed in practice: a 35-minute session (18:35→19:10, ~420k input / 62k
output tokens) was captured as a 27-second stub (18:35→18:36, 12.8k / 312) and
never backfilled, because its UUID was already in `~/.halyard/codex-imported`.

This is the same failure class that hit a Gemini session earlier. Gemini self-
heals because its rows are collapsed at read time by session id; Codex has no
such collapse and no growth check, so the stub is permanent.

## What changes

1. **Growth-aware re-import.** Track each rollout file's size alongside its UUID
   in `codex-imported`. Re-import a session when its file has grown since the
   last import (or when it has never been seen). A bare-UUID entry from the old
   format is treated as "re-check once".
2. **Tag Codex rows with the session UUID** (`job_id=codex:<uuid>`) so redundant
   rows for one session can be collapsed.
3. **Collapse redundant Codex rows at read time**, keyed by session UUID, keeping
   the most complete row — mirroring the existing Gemini collapse. This makes
   repeated re-imports of a growing session idempotent (no double-count).

## Impact

- Affected: `src/halyard/collectors/codex_app.py` (state format + dedup),
  `src/halyard/ai_log.py` (generalize the read-time collapse to Codex).
- `codex-imported` gains a `<uuid>\t<size>` line format; old bare-UUID files are
  read transparently and upgraded on next write.
- No change to the public log line format beyond an added `job_id` tag (already
  used by the Gemini importer).
- Out of scope: the Copilot importer (separate OTel ingestion path) and the
  Gemini importer (already collapse-protected).
