# Spec: Gemini session de-duplication

## Requirement: one ledger row per Gemini session at read time

A Gemini CLI session that produced several redundant `s` rows (the live hook's
per-turn cumulative snapshots and/or the importer's whole-session row) SHALL be
surfaced as exactly one canonical session by every counting surface.

### Scenario: multi-turn hook session collapses

- WHEN the Gemini hook recorded a session across N turns, each row carrying the
  running cumulative total from the whole-session history file
- THEN `parse_sessions` surfaces one row for that session id — the most complete
  (greatest input+output) — and the earlier cumulative snapshots are not counted.

### Scenario: hook + importer duplicate collapses

- WHEN a session has both a hook row (`session_id=<id>`) and an importer row
  (`job_id=gemini:<id>`) describing the same whole-session totals
- THEN they collapse to a single row; the better-attributed row (one with a
  `project`) is preferred when totals tie.

### Scenario: distinct sessions and other tools are untouched

- WHEN rows belong to different Gemini session ids, or to a non-Gemini tool
  (e.g. `claude-code` per-turn rows that are genuine increments)
- THEN no collapse occurs and every row is preserved.

### Scenario: raw log is not rewritten

- WHEN the collapse runs
- THEN it is read-time only; the original `s` lines remain in `ai-sessions.log`
  (immutable, auditable).

## Requirement: honest handling of the utility model

Capture SHALL NOT fabricate usage for a model Gemini does not persist to history.

### Scenario: utility model absent from history

- WHEN a session used a secondary utility model (e.g. `gemini-3.1-flash-lite`
  router/summarizer calls) that appears only in the terminal `/quit` summary and
  not in the session `.jsonl`
- THEN Halyard records only the models present in the history file and does not
  invent a row for the missing model; the limitation is documented.
