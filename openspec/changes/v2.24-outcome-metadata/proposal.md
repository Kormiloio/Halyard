# Proposal: v2.24 — Outcome Metadata Uplift

## Why

Halyard captures *that* AI work happened but not *whether* it connected to
engineering progress. The current session model scores 2/10 on outcome
awareness. Three gaps:

1. **Branch is a tag, not a field.** All four collectors call `current_branch()`
   at stop time but store the result as `"branch:main"` inside the `tags` list.
   Every downstream consumer — reports, dashboard, outcome sync — must parse a
   tag string instead of reading a typed field.

2. **Code delta is Gemini-only.** `code_added` and `code_removed` are
   first-class fields on `AiSession` but only the Gemini CLI collector
   populates them. Claude Code and Cursor sessions report `None`.

3. **No commit count or PR linkage.** Sessions carry no record of how many
   git commits landed in the session window, and no reference to the PR (if
   any) that the work eventually produced.

Without these signals the session log cannot answer the investor question the
strategy docs name explicitly:

> Is the AI spend producing engineering leverage?

This change moves the score from 2/10 to 6/10 by shipping the five signals
that are computable from local git + `gh` metadata only, require no new
collector work beyond the current four, and do not capture prompts, diffs, or
source code.

## What changes

### 1 — Branch as a first-class field (all collectors)

Add `branch: str | None = None` to `AiSession`. Update serialization
(`to_log_line`) and parsing (`parse_sessions`) to read/write `branch=<name>`.
Update all four collectors to write `session.branch = branch` instead of
appending to `tags`. Trust label: `captured`.

Migration: existing `tags` entries of the form `branch:*` are read as the
`branch` field by the parser during a one-time migration pass in `db.py`
(`halyard db reset` triggers it with a clear message).

### 2 — Commit count at session close (all collectors)

Add `commit_count: int | None = None` to `AiSession`. At session stop time,
call a new `git_context.commits_in_window(cwd, start, end)` function that runs:

```
git -C <cwd> log --since=<start> --until=<end> --oneline
```

and returns the line count. Write `session.commit_count = N`. Trust label:
`captured` (we counted actual commits in the window).

Graceful degradation: if the directory is not a git repo, or `git` times out
(2-second limit already used throughout `git_context.py`), `commit_count`
stays `None`. Never fails a session on a git error.

### 3 — Code delta for Claude/Cursor/Codex (calculated)

Add `code_removed: int | None = None` to complement the existing
`code_added` field. For Gemini this is already populated from the history
file. For Claude/Cursor/Codex, approximate via:

```
git -C <cwd> diff --numstat <sha-at-start> HEAD
```

where `sha-at-start` is captured at session open via a new
`git_context.head_sha(cwd)` call. Sum the added and removed columns across
all files. Trust label: `calculated` (derived from git numstat, not from tool
instrumentation).

Prerequisite: the session open path must capture `sha_at_start` and pass it
to the stop handler. This is a small change to the Claude Code and Cursor
collector start/stop flow.

### 4 — PR linkage via `halyard outcome sync`

New CLI command: `halyard outcome sync [--since <date>] [--project <slug>]`

Scans sessions in the window, groups by branch, runs:

```
gh pr list --head <branch> --json number,state,mergedAt,url
```

For each matching PR, appends an amendment record to `ai-sessions.log`:

```
a <session_hash> pr_ref=<owner/repo#nnn> pr_state=<merged|closed|open>
```

New SQLite tables (requires v2.18 migration framework):
- `outcomes` — keyed by `session_id`, holds resolved `pr_ref`, `pr_state`,
  `outcome_resolved_at`
- `pr_cache` — keyed by branch + repo, `gh` query result with 1-hour TTL

Also adds:
- `halyard outcome report` — outcome-bucketed session report
  (shipped / in-flight / abandoned / no-PR)
- `halyard outcome attribute <session-id> <pr-ref>` — manual override

All `gh` calls are gated: absence of `gh` drops `pr_ref` only; nothing else
breaks. Trust label for PR linkage: `captured`. Trust label for repeated-attempt
detection (future): `inferred`.

## What stays the same

- `ai-sessions.log` append-only invariant. Branch and commit_count are written
  at session close. PR linkage is written as amendment records by
  `halyard outcome sync`, never inline.
- SQLite cache remains a derived read model. Plain-text files are source of truth.
- The existing `tags` field is preserved on `AiSession` for other tag types.
  Only `branch:*` entries are promoted.
- Privacy contract unchanged: no prompt text, no diff content, no file paths
  (file paths appear only as counts in numstat output).

## Out of scope

- Test run detection from shell history (v3.1, too noisy for v2.24).
- Repeated-attempt detection (v3.1, needs branch-pattern analysis across
  sessions).
- Review friction signals (PR comment count, time-to-merge) — requires
  additional `gh` API calls; v3.1.
- Full outcome graph analytics (v3.0, design-partner gated).

## Prerequisites

- v2.18 must land first. `halyard outcome sync` requires the SQLite migration
  framework (`PRAGMA user_version` + migration list in `db.py`) to create the
  `outcomes` and `pr_cache` tables safely.

## Success criteria

1. On a project with git history, `halyard report` shows `branch`, `commits`,
   and `code_added` for Claude Code sessions — not only Gemini sessions.
2. `halyard outcome sync` resolves ≥80% of sessions in the last 30 days to a
   branch and ≥60% to a PR ref on a typical active project.
3. Amending a session's attribution 5 times produces exactly 1 `outcomes` row
   with the latest state.
4. `gh` absent: `halyard outcome sync` exits cleanly with a message; all other
   commands unaffected.
5. Test suite gains ≥25 new tests across field promotion, commit counting,
   numstat parsing, PR resolution, graceful degradation, and outcome reporting.
6. `halyard report` and `halyard tui` display branch and commit count for
   sessions that have them, without layout breakage for sessions that don't.
