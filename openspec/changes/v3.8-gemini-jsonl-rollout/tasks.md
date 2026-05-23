# Tasks: v3.8 — Gemini CLI `.jsonl` rollout capture

## Implementation

- [x] Extract `_aggregate_message(msg, stats_by_model)` shared reducer in
      `gemini_history.py`; rewire the legacy `.json` path to use it.
- [x] Add `_parse_jsonl_rollout(path, max_bytes)` streaming parser.
- [x] Dispatch on suffix in `parse_session_file(path, *, max_bytes=...)`.
- [x] Add `_MAX_ROLLOUT_LINE_BYTES`, `_DEFAULT_ROLLOUT_BYTES`,
      `_HOOK_ROLLOUT_BYTES` constants.
- [x] Update `find_all_session_files()` to glob `.jsonl` too.
- [x] Update `find_session_file()` + add `_session_id_of()` (first-line read
      for `.jsonl`).
- [x] Update per-project glob in `cli_importers.import_gemini`.
- [x] `gemini_cli.handle_agent_stop` passes `max_bytes=_HOOK_ROLLOUT_BYTES`.
- [x] Fix tz-aware `turn_start` crash in `handle_agent_stop` (normalise to
      local-naive) — the live-hook half of the same outage.

## Tests

- [x] JSONL: single-model, multi-model, thinking, tool calls/errors,
      no-gemini-events, header-only, `$set` end advancement.
- [x] `.json` ↔ `.jsonl` parity for the same events.
- [x] Discovery: `find_all_session_files` returns `.jsonl`;
      `find_session_file` finds `.jsonl` by id; rejects prefix-only mismatch.
- [x] Bounds: oversize single line skipped; over-budget file → `None`.
- [x] Regression: tz-aware (`Z`-suffixed) `turn_start` records instead of
      crashing, and resets state to a naive `turn_start`.

## Verification

- [x] `uv run ruff check .` && `uv run ruff format --check .`
- [x] `uv run mypy src/`
- [x] `uv run pytest` (1398 passed, +21 new tests; 1 pre-existing,
      environment-induced failure in `test_v35_claude_code_surface.py`
      unrelated to this change — surface detection reads the test runner's
      process ancestry, which is the desktop app)

## Backfill (one-time, scoped)

- [x] Backfill session `9d3f7d6b-…` into the project ledger (this session
      only — avoid double-counting the May 7 old-hook rows).

## Docs

- [x] `openspec/project.md` roadmap entry (item 62, v3.8).
- [x] `CHANGELOG.md` Fixed entry.
- [x] Tick tasks as completed.
