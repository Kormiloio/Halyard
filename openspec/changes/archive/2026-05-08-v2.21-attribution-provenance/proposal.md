# Proposal: v2.21 — Attribution Provenance

## Why this change

Session attribution in Halyard had no provenance record. The `OrgSession`
data model included an `attribution_state` field with an `"inferred"` branch,
but no collector ever wrote the `attribution:inferred` tag that would activate
it. The field was schema dead code.

This matters for two reasons:

1. **Auditability.** When a session is attributed to a project — especially via
   inference from workspace root or git — there is no record of *how* that
   attribution was determined. If the inference was wrong, there is no trail
   to investigate.

2. **Financial correctness.** Attribution determines which client or project is
   billed for AI work. An inference that silently goes wrong produces incorrect
   invoices with no indication that a guess was involved.

The specific failure mode: a developer working across three git repos in tmux
could have sessions from all three attributed to whichever repo was the last
active git inference hit. The log would show `project=client-b` with no signal
that this was inferred rather than explicit.

## What this change does

Adds an `attr_method=` KV field to the session log format. The field records
one of four values:

| Value | Meaning |
|---|---|
| `timer` | Attribution came from the active `~/.halyard/active` timer file |
| `ws_root` | Attribution inferred from workspace root (halyard.toml found walking up) |
| `git` | Attribution inferred from git remote |
| `backfill` | Attribution assigned by `assign_unattributed_sessions()` or `backfill_window()` |

This makes the `attribution_state` flag live: sessions with `attr_method=timer`
are explicit; sessions with `attr_method=ws_root` or `attr_method=git` carry
the `attribution:inferred` tag and can be reviewed.

## What this change does NOT do

- No change to how attribution is determined. The priority order (timer >
  workspace root > git) is unchanged. This change only records which path was
  taken.
- No retroactive rewriting of existing log lines. Old lines without
  `attr_method=` parse as `attr_method=None` (backward compatible).
- No new commands or user-facing changes beyond the new field appearing in
  `halyard report` session detail views.

## Key decisions

**Why a KV field rather than a separate tag?**

The existing `tags=` field is a comma-separated list that already carries
`attribution:inferred`. Adding a separate KV field for `attr_method` is
cleaner to parse (it has a defined value set; tags are free-form) and more
efficient to query (no string-split on tags just to find the attribution
method).

**Why is `attribution:inferred` still written as a tag?**

Backward compatibility. Existing code (including OrgSession) checks for the
`attribution:inferred` tag. The tag and the `attr_method=` field carry
overlapping information intentionally: the tag is for filtering, the field is
for provenance. A future cleanup can retire the tag once all consumers are
migrated.

**Why is `timer` not tagged as inferred?**

Timer attribution is explicit: the user ran `halyard start <project>` and
Halyard is honoring that explicit declaration. Workspace and git inference are
heuristics that can be wrong; timer attribution cannot be (absent a user error
in starting the timer).

## Success criteria

- All three collectors write `attr_method=` on every session they record.
- `assign_unattributed_sessions()` and `backfill_window()` write `attr_method=backfill`.
- Old log lines without `attr_method=` parse with `attr_method=None`.
- 12 new tests pass.
- ruff and mypy report no new errors.
