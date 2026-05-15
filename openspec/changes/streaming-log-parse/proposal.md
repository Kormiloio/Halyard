# Streaming `ai-sessions.log` Parser

## Summary

Change `parse_sessions()` and its sibling readers in `ai_log.py` from
whole-file (`read_text().splitlines()`) to streaming line-by-line iteration so
that a single multi-year project log doesn't have to fit fully in memory.

## Motivation

Today `parse_sessions()` loads the entire log into RAM before parsing. At
typical sizes (hundreds-to-thousands of sessions) this is fine. But the file
is append-only and grows unbounded for long-lived hubs — power users will
hit logs with tens of thousands of lines within a year. A streaming parser
keeps memory flat and improves cold-start latency for the dashboard and TUI.

## Scope

In:
- `parse_sessions()` (ai_log.py:~395)
- `_effective_session_lines()` (ai_log.py:~698)
- `_session_count_in()` (ai_log.py:~775)
- Any other reader that does `read_text().splitlines()` over a log path.

Out:
- The append/write path — already line-by-line.
- The amendment fold step still requires holding the amendment dict in memory;
  scope here is the line-iteration layer only.

## Acceptance

- `parse_sessions()` returns identical results to the current implementation
  on the existing test corpus.
- Reading a synthetic 100k-line log uses < 10 MB of resident memory and
  completes in under 1 s on a modern laptop.
- No behavior change for malformed-line quarantine or amendment folding.

## Notes

Defer until a real user reports slow dashboard refresh on a large log, or
the log corpus in test fixtures exceeds ~10k lines.
