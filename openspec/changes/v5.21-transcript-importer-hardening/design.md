# v5.21 — Design

## Attribution: transcript `cwd`, never folder names

Claude Code's `~/.claude/projects/<encoded>` folder names are a lossy encoding
(`/`, `.`, `-` → `-`); no decoder can be correct. The transcript events
themselves carry the real `cwd` per line, exactly like codex rollouts carry
`cwd` in `session_meta`/`turn_context`. `_TranscriptStats` gains a `cwd`
field (first non-empty value wins); `import_claude_sessions` resolves the
target with `find_project_dir(start=Path(cwd))`. **Tracked projects only**
(owner decision, 2026-06-10): there is deliberately no hub fallback — a
dry-run of the full corpus showed 1,648 of 1,656 candidate sessions
(headless/observer transcripts, dead cwds) would land unattributed in the
hub ledger, ~90% noise. A transcript that resolves to no initialised
project is skipped, never guessed at. Folder iteration is only used to
*find* `*.jsonl` files.

## Dedup: three layers, matching existing patterns

1. **Ledger-covered sessions are skipped at import time.** Per target dir
   the importer parses the ledger once (`_existing_coverage`, patterned on
   `copilot._otel_captured_ids`) and collects, from every claude-code row
   not written by this importer (`job_id=claude:` rows excluded so a grown
   live transcript can re-import past its own earlier row): the
   `session_id` set — a precise skip for modern rows — and the `[start,
   end]` windows — a coarse skip for the legacy era whose hook rows carry
   neither `session_id` nor `source` (verified live: 430 claude-code rows
   in the Halyard ledger, only 163 with a session id). The Stop hook
   records *per-turn delta* rows — a whole-transcript import row on top of
   those double-counts every turn; its own watermark catch-up
   (`_last_recorded_end`) already heals intra-session gaps. Known
   limitations: a session whose hooks died mid-way stays partially captured
   rather than double-counted, and a missed session running in parallel
   with a hooked one is skipped by the overlap check — both err toward
   never double-counting billing evidence.
2. **State file `~/.halyard/claude-imported` uses the codex v5.2 format**
   (`<id>\t<size>` per line): a transcript re-imports when its file has grown
   (live session imported mid-flight), is skipped when unchanged. Only ids
   actually appended are recorded; legacy bare-id lines parse as size-None
   and re-check once.
3. **Read-time collapse for re-imports.** Imported rows carry
   `job_id=claude:<session_id>`; `_claude_session_key` in `ai_log.py` matches
   **only** that job-id prefix (no `session_id` fallback — that would collapse
   the hook's per-turn rows, destroying real data; this is the deliberate
   asymmetry vs `_gemini_session_key`, whose hook rows are cumulative
   snapshots and safe to collapse). `_canonical_gemini_row`'s max-tokens rank
   picks the latest re-import naturally.

## Plausibility guard

`_MAX_SESSION_SECONDS` returns to `12 * 3600`. The 7-day bump defeated the
guard's documented purpose (frozen session-starts → synthetic multi-day rows)
for every collector at once. The importer applies the same
`session_has_evidence` / `session_is_implausible` /
`session_is_synthetic_telemetry` gauntlet as the stop hook; a >12h transcript
is skipped, not stretched to fit. (Long-lived windows contain mostly idle
time; importing them as one row corrupts duration-based reporting. Active-
period segmentation is the principled future fix.)

## Costing and row construction

Mirror `handle_stop_hook`: `calculate_cost(model, input, output, cache_read,
cache_write)`; when the transcript is multi-model, prefer
`_breakdown_cost(model_breakdown)` and `primary_model`. Timestamps come from
`stats.start_dt`/`end_dt` (already UTC→local-naive via `_transcript_ts`,
ADR-0001 compliant). `source="import"`, `telemetry_source=
"claude-code-transcript"`, `telemetry_trust="observed"`, project attribution
via `infer_project_with_source(cwd)` with the hook's `attribution:inferred`
tagging, git enrichment (`current_branch`, `commits_in_window`) from the
transcript's cwd when it exists on disk.

## Copilot parser

- `_apply_patch` keeps the list-growing behaviour (kind-1/2 patches that
  target `requests[N]` beyond the snapshot now materialise) — that plus
  response-part aggregation is the real "recent VS Code" fix. The unused
  `enumerate` index goes (B007).
- The `range(max(len(req_list), max_idx))` phantom loop is removed: because
  `_apply_patch` grows lists, every patched index already exists in the
  reconstructed `requests`; padding with `{}` only fabricated user turns.
- Response evidence per request prefers the aggregated parts
  (`all_response_parts[i]`), falling back to the reconstructed state.

## Operational repair (one-time, performed with this change)

Hub daemon stopped during surgery; every file backed up as
`<name>.bak-<UTC-stamp>` first.

- Remove `claude-code` + `source=import` rows: 1,841 (home ledger — itself a
  May test-project that became the misattribution sink), 31 (Halyard repo),
  16 (hub).
- Compact byte-identical duplicate `s` rows keeping first occurrence (repo
  ledger: ~415 lines, dominated by the same three gemini sessions re-appended
  by every 30-minute timer tick; read-time collapse hid them from reports but
  the file growth was unbounded).
- Reset `~/.halyard/claude-imported`.
- The `io.kormilo.halyard.import` launchd timer was booted out before repair
  and re-bootstrapped only after the fixed code passed all gates.
