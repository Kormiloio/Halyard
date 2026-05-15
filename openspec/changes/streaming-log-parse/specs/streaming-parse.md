# Spec: Streaming `ai-sessions.log` Parser

## Requirement: `parse_sessions()` MUST iterate the log file line-by-line.

The reader path through `ai_log.py` MUST NOT call `Path.read_text()` on the
full log file and split in memory.  It MUST open the file once and iterate
its lines through Python's file iterator (`for line in fh:`), so memory
usage is bounded by the longest single line, not by the total log size.

### Scenario: Identical results to the prior implementation

WHEN `parse_sessions(project_dir)` is called against an existing fixture
log used by the test suite
THEN the returned list is identical to the list produced by the prior
whole-file reader
AND the order of sessions matches the file order
AND amendments fold in the same order as before.

### Scenario: Malformed lines still quarantined

WHEN a malformed `s` line is encountered during streaming parse
THEN it is quarantined via `_write_quarantine()` exactly as before
AND parsing continues at the next line.

### Scenario: Bounded memory on a large log

WHEN `parse_sessions()` runs on a 100 000-line synthetic log
THEN peak resident memory growth for the parser stays under 50 MB above
the baseline
AND wall time stays under 2 s on a developer laptop (smoke threshold; not
a hard performance contract).

### Scenario: Sibling readers also stream

WHEN `_session_count_in(path)` or `_effective_session_lines()` reads from
a log path
THEN it uses the same streaming pattern — no `read_text().splitlines()`
on the full file
AND it accepts either a `Path` argument or a pre-collected line iterable,
to preserve the in-memory paths that already build content (e.g. lines
constructed by `_append_lines()` callers).

### Scenario: Reader is robust to a writer appending mid-read

WHEN a second process appends a new session line to the log file while a
reader is iterating it
THEN the reader either sees the new line or doesn't, but never crashes,
returns a partial line, or raises a decode error
AND the next `parse_sessions()` call picks up any session the prior call
missed.
