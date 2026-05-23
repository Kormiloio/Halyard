# Spec: coverage canary for Cursor and Windsurf

## Requirement: monitor Cursor and Windsurf capture (best-effort)

`halyard doctor` SHALL warn when Cursor or Windsurf shows on-disk activity newer
than its last captured ledger row by more than a coarse grace, using storage
mtimes only (never parsing their internal SQLite/leveldb stores).

### Scenario: storage older than capture → no warning

- WHEN a tool's storage was last modified before (or near) its last captured row
- THEN no warning is emitted (capture is current — or the tool is simply unused).

### Scenario: recent activity, stale capture → warning

- WHEN a tool's storage mtime is newer than its last captured row by more than
  the coarse grace, AND the tool has at least one captured row (baseline)
- THEN a `warning` (never `error`) is emitted naming the lag and the one-line fix,
  worded to acknowledge it is a best-effort signal for a hook-only tool.

### Scenario: never captured → no warning

- WHEN a tool has no captured row at all (no baseline)
- THEN no warning is emitted (a never-used tool is not a regression).

### Scenario: storage absent → no warning

- WHEN the tool's storage directory does not exist
- THEN no warning is emitted.

## Requirement: no internal-format parsing

The check SHALL rely only on file/directory modification times, never on reading
or decoding Cursor's `state.vscdb` or Windsurf's Cascade store contents.
