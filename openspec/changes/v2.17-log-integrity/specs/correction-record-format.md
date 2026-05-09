# Spec: Correction-Record Line Format

## Purpose

Halyard's `ai-sessions.log` is append-only. To correct attribution or
metadata after the fact, the log uses *amendment* lines (`a`) that
reference an original session by hash and override fields at parse time.

This preserves the audit trail (you can always see what the original
record said) and makes the log a genuine append-only stream that other
tools can safely emit.

## Format

```
a <session_hash> <key=value> [<key=value> ...]
```

Where:

- `a` is the line type marker.
- `<session_hash>` is the first 12 hex characters of
  `sha256(<original_s_line_stripped>)`.
- Each `<key=value>` is space-separated, value-trim-quoted only if it
  contains spaces.

Example:

```
s 2026-01-01T09:00:00 2026-01-01T09:30:00 claude-code claude-sonnet-4-6 10000 2000 0.085
a a3f9c1d2e4b7 project=acme:auth source=backfill confirmed_at=2026-01-08T14:00:00
```

## Allowed keys (v2.17)

| Key            | Type       | Notes                                           |
|----------------|------------|-------------------------------------------------|
| `project`      | string     | Client:project slug                             |
| `source`       | enum       | `backfill`, `manual`, `confirmed`, `correction` |
| `confirmed_at` | ISO 8601   | When the amendment was made                     |
| `note`         | string     | Free-form, surfaced in dashboard tooltips       |

Future versions add: `pr_ref`, `pr_state`, `branch`, `commit_count`,
`code_added`, `code_removed`, etc. (See v3.0 outcome graph spec.)

Unknown keys are ignored at parse time, never error. Forward-compatible.

## Fold semantics

When parsing the log:

1. Iterate lines in file order.
2. For each `s` line, compute its hash and store the resulting
   `AiSession` keyed by hash.
3. For each `a` line, append its key-value pairs to a list keyed by the
   referenced hash.
4. After the scan, for each session, apply amendments in file order.
   Last write wins per key.
5. An amendment referencing a hash that was never seen is silently
   ignored (no orphan error). This handles the case where someone
   amends, then later truncates the log.

The fold is deterministic and reproducible: the same log produces the
same parsed sessions every time.

## Hash stability

The hash is computed on the **raw `s` line as written**, including
trailing key=value attribution that may have been written by the
collector. This means the hash never changes for a given line.

If a future tool needs to amend a session whose original `s` line is
not visible (e.g. log truncation), it must store and reference the
hash separately.

## Locking

Writers must hold an exclusive flock on the log file while appending an
`a` line, identical to appending an `s` line. See `locked_file` in
v2.17.

## Compatibility

Pre-v2.17 logs contain only `s` lines and parse identically. Mixed logs
where some attribution was set via the legacy `write_text` path and some
via `a` records are handled correctly: legacy attribution lives on the
original `s` line; new attribution rides on `a` records and overrides
it.

A hidden `halyard log normalize` command (deferred) can rewrite a
legacy log to canonical form: all original `s` lines stripped of
post-hoc attribution, all corrections moved into `a` records. Not
required for v2.17 to function.

## Trust labels and amendments

When an amendment changes attribution, the resulting session's trust
label is updated:

- Original `captured` + amendment `source=manual` → label `mixed`
- Original `inferred` + amendment `source=manual` → label `captured` for
  attribution, original label for everything else
- Multiple amendments → label `mixed`

The dashboard exposes amendment history on session detail tooltip:
"Attribution changed 2 times. Last change 2026-01-09 by manual
correction."
