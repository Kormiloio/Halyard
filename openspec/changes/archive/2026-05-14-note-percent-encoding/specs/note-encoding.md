# Spec: Percent-Encoding for Free-Text Log Fields

## Requirement: New writes MUST percent-encode free-text fields containing
spaces, control characters, or `=`.

The `note` and `resume_command` fields in `AiSession.to_log_line()` MUST be
encoded with `urllib.parse.quote(value, safe="")`. The result is then safe
to embed verbatim in a space-delimited log line. The encoded form is the
canonical on-disk representation for new writes.

### Scenario: Round-trip preserves underscores

WHEN a session is written with `note="snake_case literal"` (mixed
underscore and space)
THEN the encoded form on disk is `note=snake_case%20literal`
AND `parse_sessions()` returns the session with `note == "snake_case literal"`
AND the literal underscore is preserved exactly, not collapsed with spaces.

### Scenario: Round-trip preserves percent signs

WHEN a session is written with `note="cost: 50% off"`
THEN the encoded form on disk is `note=cost%3A%2050%25%20off`
AND `parse_sessions()` returns the session with `note == "cost: 50% off"`.

### Scenario: Round-trip preserves unicode

WHEN a session is written with `note="café ☕"`
THEN the encoded form is `note=caf%C3%A9%20%E2%98%95`
AND parse round-trips to the exact same string.

## Requirement: Reads MUST accept BOTH the legacy underscore encoding and the
new percent encoding.

Existing logs already contain lines written by the old encoder
(`note=snake_case_name` where `_` could be a space or a literal
underscore). Halyard MUST continue to read those lines without quarantining
them.

### Scenario: Legacy underscore lines parse unchanged

WHEN a log file contains a pre-change line `note=quick_check resume_command=halyard_resume_acme`
THEN `parse_sessions()` returns the session
AND the `note` value is `"quick check"` (legacy decode: underscores → spaces)
AND no quarantine entry is written.

### Scenario: Encoding heuristic prefers percent decoding when present

WHEN a stored value contains any `%XX` escape
THEN the decoder uses `urllib.parse.unquote()` and returns the result
verbatim — including any literal underscores untouched.

### Scenario: Encoding heuristic falls back to legacy when no percent escapes
present

WHEN a stored value contains no `%` character at all
THEN the decoder uses the legacy rule: `value.replace("_", " ")`.

## Requirement: `session_hash()` MUST be stable across the encoding change.

The hash is computed over the raw stored line bytes, so any pre-change
line will produce the same hash before and after the migration.

### Scenario: Pre-change s-lines remain amendable

WHEN an `a` amendment record references the hash of a pre-change `s` line
THEN that amendment continues to fold correctly after the encoder switch
AND no hash recomputation or backfill is required.

## Out of Scope

- Migrating existing `s` lines to percent-encoded form (would break
  amendment-record hashes — covered separately).
- Changing the positional `tool` / `model` fields, which are sanitised via
  `_safe_field()` and don't carry user free-text.
