# Spec: v2.24 — `halyard outcome sync` Command

## Command surface

```
halyard outcome sync [--since DATE] [--project SLUG] [--dry-run]
halyard outcome report [--since DATE] [--project SLUG]
halyard outcome attribute SESSION_ID PR_REF
```

All three live under a new `outcome` Typer sub-app registered in `cli.py`.

---

## `halyard outcome sync`

**Purpose:** scan recent sessions, resolve each to a PR (if any) via `gh`,
write amendment records.

### WHEN called with no flags

**THEN** scans sessions from the last 30 days across all known projects.

### WHEN `--since DATE` is provided

**THEN** scans sessions from DATE forward. Accepts any dateparser-parseable
string ("last week", "2026-05-01", etc.).

### WHEN `--project SLUG` is provided

**THEN** scans only sessions attributed to that project slug.

### WHEN `--dry-run` is provided

**THEN** prints what amendment records would be written, writes nothing.

### Resolution algorithm

For each unique `(branch, repo_remote)` pair in the scanned sessions:

1. Check `pr_cache` — if a cache entry exists and is < 1 hour old, use it.
2. Otherwise run:
   ```
   gh pr list --head <branch> --json number,state,mergedAt,url --limit 5
   ```
3. Store result in `pr_cache` with `fetched_at = now()`.
4. For each session on that branch, pick the best matching PR (prefer the
   PR whose creation date is closest to the session end time).
5. Append amendment record:
   ```
   a <session_hash> pr_ref=<owner/repo#nnn> pr_state=<merged|closed|open>
   ```
   If no PR matched: append `a <session_hash> pr_state=none`.
6. Write to `outcomes` table in SQLite cache.

### WHEN `gh` is not installed or returns a non-zero exit code

**THEN** print a single warning line: `gh not available — skipping PR
resolution`. All other fields (branch, commit_count, code_added) are
unaffected.

### WHEN a session already has `pr_ref` set (from a prior sync)

**THEN** skip it unless `--force` is passed. This prevents re-querying PRs
that have already been resolved.

---

## `halyard outcome report`

**Purpose:** display sessions bucketed by outcome.

Output format:

```
Outcome Report — last 30 days

  Shipped (PR merged)       12 sessions  $4.21
  In-flight (PR open)        3 sessions  $1.05
  Abandoned (PR closed)      1 session   $0.18
  No PR detected            18 sessions  $2.44
  Not synced                 6 sessions     —

Run `halyard outcome sync` to resolve unsynced sessions.
```

Trust labels follow the same convention as `halyard report`. PR-linked rows
are `captured`; "No PR detected" rows that were synced are also `captured`
(we checked and found nothing). "Not synced" rows have no trust label —
explicitly shown as `—`.

---

## `halyard outcome attribute SESSION_ID PR_REF`

**Purpose:** manual override for cases where the heuristic missed.

`SESSION_ID` — the 12-char session hash (shown in `halyard report` and TUI).
`PR_REF` — any of: `#42`, `owner/repo#42`, full GitHub URL.

**THEN** appends:
```
a <session_hash> pr_ref=<normalized_ref> pr_state=<fetched_from_gh_or_open>
```

If `gh` is available, fetches the current PR state. If not, writes
`pr_state=open` as a conservative default with a note to re-run
`halyard outcome sync` to update it.
