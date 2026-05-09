# Spec: v2.24 — Collector Changes

## All four collectors: branch field promotion

**WHEN** a session stop event fires in any collector (Claude Code, Cursor,
Gemini CLI, Codex):

**THEN** the collector sets `session.branch = current_branch(cwd)` as a
typed field, and does NOT append `f"branch:{branch}"` to `session.tags`.

The `current_branch()` function already exists in `git_context.py` and is
already called by all four collectors. This is a one-line change per
collector: swap `tags` append for field assignment.

## All four collectors: commit_count at stop

**WHEN** a session stop event fires:

**THEN** the collector calls `git_context.commits_in_window(cwd, start, end)`
and writes the result to `session.commit_count`.

New function in `git_context.py`:

```python
def commits_in_window(cwd: Path, start: datetime, end: datetime) -> int | None:
    """Return the number of commits whose author date falls in [start, end].

    Returns None on any git error, timeout, or if cwd is not a git repo.
    Never raises.
    """
```

Implementation: `git -C <cwd> log --since=<start.isoformat()>
--until=<end.isoformat()> --oneline` piped through `wc -l`. Timeout: 2s
(consistent with all other `git_context` calls).

## Claude Code + Cursor + Codex: code delta via numstat

**WHEN** a session opens (start event):

**THEN** the collector captures `sha_at_start = git_context.head_sha(cwd)`.

New function in `git_context.py`:

```python
def head_sha(cwd: Path) -> str | None:
    """Return the current HEAD SHA (short, 12 chars), or None."""
```

**WHEN** the session closes (stop event) AND `sha_at_start` is not None:

**THEN** the collector runs:

```
git -C <cwd> diff --numstat <sha_at_start> HEAD
```

Parses the output (two integers per line: added, removed, path). Sums all
lines. Writes to `session.code_added` and `session.code_removed`. Trust
label: `calculated`.

**WHEN** `sha_at_start` is None OR git errors OR the diff produces no output:

**THEN** `session.code_added` and `session.code_removed` remain `None`. No
failure.

**Gemini CLI:** already populates `code_added` from the history file with
trust label `captured`. Do not replace with the numstat approximation —
the history file is more accurate. Skip the numstat path for Gemini.

## Edge cases

- **Detached HEAD:** `current_branch()` already returns `None` in this case.
  `commits_in_window` is still called; it returns a count against the detached
  ref.
- **No git repo in cwd:** all three new calls return `None` gracefully.
- **Monorepo / multi-project repo:** numstat covers the whole repo delta in
  the session window, not just files the developer touched. This is documented
  as a known limitation; trust label `calculated` conveys it.
- **Long-running sessions spanning many commits:** `commits_in_window` counts
  all of them. No cap — the number is informational.
