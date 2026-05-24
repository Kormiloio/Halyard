# Design — v5.2 Codex importer growth-aware re-import

## Root cause

`import_codex_sessions` dedups on a permanent set of UUIDs
(`~/.halyard/codex-imported`). A session captured mid-write is recorded as a
partial snapshot and its UUID is never reconsidered, so the remainder of the
session is lost. Unlike Gemini, Codex rows carry no session id, so there is no
read-time collapse to reconcile a later, fuller row.

## Approach

Mirror the Gemini model: allow multiple rows per session over the session's
life and collapse them at read time, while avoiding needless re-work via a
growth check.

### 1. Growth-aware dedup (`codex_app.py`)

`codex-imported` lines become `"<uuid>\t<size>"`, where `size` is the rollout
file's byte size at import time.

- Reader (`_load_imported_state`) returns `dict[str, int | None]`. A legacy
  bare-UUID line parses to `{uuid: None}`.
- Skip a session only when its UUID is present **and** the recorded size equals
  the file's current size. A grown file (`current > recorded`), an unknown UUID,
  or a recorded `None` (legacy) triggers (re)import.
- On save, every present rollout's `(uuid, current_size)` is written, so a
  re-import updates the fingerprint. The existing prune-to-present-files logic is
  retained to bound state growth.

### 2. Tag Codex rows (`codex_app.py`)

The importer sets `session.job_id = f"codex:{uuid}"` before appending. The
`job_id` field already exists on `AiSession` and is what the Gemini importer uses
(`gemini:<id>`), so no schema change is needed.

### 3. Generalize the read-time collapse (`ai_log.py`)

`collapse_gemini_sessions` is kept as the public name (3 callers + the v3.14
tests) but its key function is generalized:

- `_redundant_session_key(s)` returns a namespaced key — `"gemini:<id>"` for
  Gemini rows (via the existing `_gemini_session_key`) or `"codex:<uuid>"` for
  Codex rows whose `job_id` starts with `codex:` — else `None`. Namespacing
  prevents any cross-tool key collision.
- The canonical-row picker is unchanged: most complete wins (max input+output),
  ties prefer an attributed row, then the wider window, then larger cache_read.

Because the picker keeps the max-token row, importing a session repeatedly as it
grows is idempotent: the newest, fullest row always wins and the earlier stubs
collapse away. Read-time only — raw lines stay in the log.

## Alternatives considered

- **Defer import until the file is idle (mtime staleness).** Simpler, but never
  captures a still-open session and adds a tunable delay. The growth+collapse
  approach surfaces progress immediately and matches the Gemini design already
  in the codebase.
- **Rewrite the log line in place on growth.** Breaks the append-only log
  invariant the rest of the system relies on.

## Verification

- New tests in `tests/` cover: re-import when a rollout grows; collapse of two
  Codex rows for one UUID to the fuller one; legacy bare-UUID state triggers a
  re-check; an unchanged file is still skipped (no duplicate work).
- Existing v3.14 Gemini collapse tests must stay green (generalization is
  additive).
- ruff + ruff format + mypy clean; full suite green.
