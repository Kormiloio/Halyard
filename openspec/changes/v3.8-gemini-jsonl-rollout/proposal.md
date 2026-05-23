# Proposal: v3.8 — Gemini CLI `.jsonl` rollout capture

## Why this exists

Halyard's Gemini collector silently stopped recording sessions. The last
Gemini row in any `ai-sessions.log` is dated **2026-05-07**; every Gemini
CLI session since has produced **zero ledger entries** despite the hooks
firing and a full transcript being captured on disk.

Root cause: Gemini CLI changed its on-disk session-history format. Older
versions wrote a single-object checkpoint file
(`~/.gemini/tmp/<slug>/chats/session-*.json`) containing a `messages`
array. Newer versions (observed on gemini-cli 0.42→0.43) write a
**line-delimited rollout log** (`session-*.jsonl`): one header line, then
one JSON event per line (`info` / `user` / `gemini`), with `$set` patch
lines updating `lastUpdated`.

`gemini_history.py` only understands the old `.json` format, and three
independent guards reject the new files:

1. **Glob miss** — `find_all_session_files()` / `find_session_file()` glob
   `session-*.json`, which never matches `session-*.jsonl`.
2. **Whole-file size cap** — `_read_capped()` refuses files over 25 MB; a
   real rollout for a long session is hundreds of MB (one observed session
   was 825 MB) because Gemini embeds tool-call results inline.
3. **Format mismatch** — `parse_session_file()` does a single
   `json.loads()` on the whole file expecting one object; a JSONL file is
   not a single JSON document.

Because both the importer (`halyard import-gemini`) and the live hook
(`gemini_cli.handle_agent_stop`) route through `gemini_history.py`,
repairing the parser fixes both capture paths at once.

## What changes

- **JSONL rollout parsing** in `gemini_history.parse_session_file`: detect
  `.jsonl` and parse it as a stream (header line → session id / start;
  `gemini` events → per-model token + tool-call stats; `$set` /event
  timestamps → end). The per-event token/tool schema is byte-identical to
  the old `messages` entries, so the aggregation logic is shared verbatim
  between the two formats.
- **Bounded streaming** for `.jsonl`: read line by line (memory-safe — the
  observed max single line is 0.8 MB), with a per-line byte cap that skips
  pathological lines and a total-bytes budget. The hook passes a tight
  budget so a multi-hundred-MB rollout degrades gracefully to the
  accumulated `gc-session` token state instead of stalling the host tool;
  the importer uses a generous budget so it can fully parse large sessions.
- **Discovery globs** updated to include `.jsonl` in
  `find_all_session_files()`, `find_session_file()`, and the per-project
  glob in `cli_importers.import_gemini`.
- **`.json` path unchanged** — the 25 MB whole-file cap and single-object
  parse stay exactly as-is for legacy checkpoint files.

## Also fixed: `AfterAgent` recorded nothing (tz-aware crash)

Investigation into "why no Gemini ledger rows since 2026-05-07" found a
second, independent defect — the live-hook half of the same outage. The
`gc-session` `turn_start` is written from Gemini's SessionStart payload
timestamp, which is now **tz-aware** (trailing `Z`), e.g.
`2026-05-23T00:51:53.687Z`. `handle_agent_stop` does
`datetime.fromisoformat(turn_start)` (→ an aware datetime) and then
`now - start` with `now = datetime.now()` (naive-local), which raises
`TypeError: can't subtract offset-naive and offset-aware datetimes`. The
`cli_hooks` crash backstop swallows it, so every `AfterAgent` fire silently
records nothing and never resets state — `turn_start` froze at the session
start for 16 hours. `AfterModel` survives because it does no datetime math
(which is why `gc-session` still accumulated tokens). This is the same
tz-aware/naive class as v2.56 P1-a; the fix normalises `start` to local-naive
(the v2.29 collector convention). Bug-class, so folded into this changeset
with a regression test rather than a separate one.

## Out of scope

- Changing the rollout's inline-tool-output bloat (an upstream Gemini
  behaviour).
- The launchd reapply glue (`halyard-gemini-hook-reapply.sh`) that re-adds
  hooks an external VS Code extension strips — local, not in the repo.

## Success criteria

- `halyard import-gemini` discovers and parses `session-*.jsonl` rollouts
  and writes correct per-model token / tool-call / interaction telemetry.
- The 825 MB session `9d3f7d6b-…` parses without OOM and is backfilled
  into the project ledger.
- Legacy `.json` checkpoint parsing is byte-for-byte unchanged.
- ruff, mypy, and the full test suite pass; new tests cover the JSONL
  schema, discovery, oversize-line skipping, and the budget cutoff.

## Risks and trade-offs

- **Re-parse cost in the hook** — the live hook re-parses the growing
  rollout each turn (O(n²) over a session). Mitigated by the tight hook
  budget that falls back to the accumulator on large files; correctness is
  preserved either way because `AfterModel` already captures accurate
  tokens.
- **Upstream format drift** — the rollout schema is undocumented and may
  change again. The v2.59 collector schema-drift canary already surfaces a
  sustained capture regression as a `doctor` warning.
