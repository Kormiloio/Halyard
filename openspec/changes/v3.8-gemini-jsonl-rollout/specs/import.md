# Spec: Gemini `.jsonl` rollout capture

## Requirement: parse the rollout format

The Gemini history parser SHALL read Gemini CLI's line-delimited rollout
log (`session-*.jsonl`) in addition to the legacy single-object checkpoint
(`session-*.json`).

### Scenario: rollout with model events

- WHEN `parse_session_file` is given a `.jsonl` file whose header line
  carries `sessionId`/`startTime` and whose `type=="gemini"` event lines
  carry `model` and `tokens`
- THEN it returns a `GeminiSessionSummary` with the session id, start, and
  per-model input/output/cache/thinking totals aggregated from the events
- AND the totals equal those produced by an equivalent legacy `.json`
  checkpoint containing the same events as its `messages` array.

### Scenario: end time from `$set` and event timestamps

- WHEN a rollout contains `{"$set":{"lastUpdated":...}}` patch lines
  and/or per-event `timestamp` fields
- THEN the summary `end` reflects the latest of those times.

### Scenario: legacy checkpoint unchanged

- WHEN `parse_session_file` is given a `.json` checkpoint
- THEN it parses it exactly as before (single `json.loads`, 25 MB cap).

## Requirement: bounded, memory-safe streaming

Rollout parsing SHALL be bounded so a large or hostile file cannot exhaust
memory or stall the host tool.

### Scenario: large rollout parses without loading the whole file

- WHEN a `.jsonl` rollout is hundreds of MB but each line is small
- THEN `parse_session_file` (with the default budget) parses it by
  streaming, without loading the entire file into memory.

### Scenario: pathological single line is skipped

- WHEN a single rollout line exceeds the per-line byte cap
- THEN that line is skipped and parsing continues with the remaining lines.

### Scenario: file over the budget returns None

- WHEN cumulative bytes read exceed the caller's `max_bytes` budget
- THEN `parse_session_file` returns `None` (the hook then falls back to its
  accumulated `gc-session` token state).

## Requirement: discovery includes `.jsonl`

Session-file discovery SHALL find `.jsonl` rollouts.

### Scenario: find_all_session_files

- WHEN `find_all_session_files` scans `~/.gemini/tmp/*/chats/`
- THEN it returns both `session-*.json` and `session-*.jsonl` files.

### Scenario: find_session_file by id

- WHEN `find_session_file` is given a session id whose rollout is a
  `.jsonl` file
- THEN it returns that file only after confirming the full `sessionId` on
  the header line matches (a prefix-only match is rejected).

### Scenario: import-gemini current-project discovery

- WHEN `halyard import-gemini` resolves the current project's Gemini slug
- THEN it globs both `session-*.json` and `session-*.jsonl` in that slug's
  `chats/` directory.
