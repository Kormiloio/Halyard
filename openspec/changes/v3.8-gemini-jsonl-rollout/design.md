# Design: v3.8 — Gemini CLI `.jsonl` rollout capture

## Format comparison

**Legacy checkpoint (`session-*.json`)** — one JSON object:

```json
{ "sessionId": "...", "startTime": "...", "lastUpdated": "...",
  "messages": [ {"type":"user","content":"..."},
                {"type":"gemini","model":"...","tokens":{...},"toolCalls":[...]} ] }
```

**Current rollout (`session-*.jsonl`)** — line-delimited:

```
{"sessionId":"...","projectHash":"...","startTime":"...","lastUpdated":"...","kind":"main"}
{"id":"...","timestamp":"...","type":"info","content":"..."}
{"$set":{"lastUpdated":"..."}}
{"id":"...","timestamp":"...","type":"user","content":[{"text":"..."}]}
{"id":"...","timestamp":"...","type":"gemini","model":"...","tokens":{"input":N,"output":N,"cached":N,"thoughts":N,"tool":N,"total":N},"toolCalls":[...]}
```

The **per-event** `type` / `model` / `tokens` / `toolCalls` schema is
identical to the legacy `messages[]` entries. Only the framing differs:
a header line instead of top-level `sessionId`/`startTime`, `$set` patch
lines for `lastUpdated`, and one event per line instead of an array.

## Approach

1. **Extract a shared aggregator.** Factor the per-message reducer out of
   `parse_session_file` into `_aggregate_message(msg, stats_by_model)` that
   mutates the per-model stats dict and returns `(is_user, is_assistant)`.
   Both the `.json` and `.jsonl` paths call it, guaranteeing identical
   token/cache/thinking/tool accounting (including the cache-inclusive
   `normalise_input` rule).

2. **Dispatch on suffix** in `parse_session_file(path, *, max_bytes=...)`:
   - `.jsonl` → `_parse_jsonl_rollout(path, max_bytes)`
   - otherwise → existing single-object path (unchanged).

3. **`_parse_jsonl_rollout`** streams the file:
   - Open in text mode, iterate lines, tracking cumulative bytes; abort
     (return `None`) if cumulative bytes exceed `max_bytes`.
   - Skip any single line longer than `_MAX_ROLLOUT_LINE_BYTES` (pathological
     / corrupt) without parsing it.
   - First dict line carrying `sessionId` → header: capture `session_id`,
     `start` (`startTime`), `end` (`lastUpdated`).
   - `{"$set": {...}}` lines → if they carry `lastUpdated`, advance `end`.
   - Event lines → `_aggregate_message`; also advance `end` from the event
     `timestamp` so a rollout missing `$set` still gets a real end time.
   - Build the same `GeminiSessionSummary` and call `_derive()`.
   - `codeStats` does not exist in the rollout → `code_added/removed` stay
     `None` (graceful, same as a `.json` without `codeStats`).

4. **Bounds / safety.**
   - `.json`: `_MAX_HISTORY_BYTES = 25 MB` whole-file cap — unchanged.
   - `.jsonl`: streaming, so memory is bounded by the longest line, not the
     file. `_MAX_ROLLOUT_LINE_BYTES = 16 MiB` (observed real max 0.8 MB).
     `_DEFAULT_ROLLOUT_BYTES = 1 GiB` default budget for `parse_session_file`
     (covers the 825 MB session). `gemini_cli.handle_agent_stop` passes
     `max_bytes = _HOOK_ROLLOUT_BYTES = 64 MiB` so the per-turn hook never
     stalls on a huge rollout — it falls back to the `gc-session`
     accumulator, which already holds accurate tokens from `AfterModel`.
   - Symlinks are still refused (`os.path.islink`).

5. **Discovery.**
   - `find_all_session_files()` → glob both `session-*.json` and
     `session-*.jsonl`.
   - `find_session_file(session_id)` → glob both extensions; verify the full
     id via a new `_session_id_of(path)` helper that reads only the **first
     line** for `.jsonl` (cheap) and parses the whole capped object for
     `.json`. Recency tie-break (`_safe_mtime`) is unchanged.
   - `cli_importers.import_gemini` per-project glob → add `session-*.jsonl`.

## Why not raise the 25 MB cap for everything?

The cap exists so an attacker-staged multi-GB file can't OOM the
importer/hook (`~/.gemini/tmp` is world-writable). For a single-object
`.json` we must load the whole file to parse it, so the cap stays. For
`.jsonl` we stream, so memory is bounded by one line regardless of file
size — a different, larger budget is safe there.

## Backfill

`import-gemini` would import every un-imported halyard-slug rollout,
including the **2026-05-07** sessions that are already in the ledger as
old-hook fallback rows (no `session_id`, so the importer's `gemini:` dedup
can't see them). Importing those would double-count May 7. Therefore the
one-time backfill is scoped to the target session `9d3f7d6b-…` only;
the importer's normal dedup protects all future runs because new rows carry
`job_id=gemini:<id>`.

## Test plan

- JSONL: single-model, multi-model, thinking tokens, tool calls/errors,
  no-gemini-events, header-only, `$set` end advancement.
- Discovery: `find_all_session_files` returns `.jsonl`; `find_session_file`
  finds a `.jsonl` by id and rejects a prefix-only id mismatch.
- Bounds: a line over the per-line cap is skipped; a file over the budget
  returns `None`.
- Parity: a `.json` and an equivalent `.jsonl` produce identical
  `GeminiSessionSummary` token/tool/interaction fields.
