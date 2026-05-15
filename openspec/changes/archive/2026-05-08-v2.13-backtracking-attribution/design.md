# Design

## Window matching

A session matches a timeclock window if:

```
session.start >= window.start AND session.start < window.end
```

Using `session.start` (not end) as the anchor is consistent with how `confirm-attribution`
and `infer_project_attribution` in `ledger.py` work today.

## Auto-attribution on stop

In `cli.py stop` command, after writing the `o` line and removing the active
file:

1. Read all closed timeclock entries from the project's `time.timeclock`.
2. Find the entry that just closed (latest entry for the stopped slug).
3. Call `backfill_window(project_dir, window_start, window_end, project_slug)`.
4. Print attributed count if > 0.

`backfill_window` lives in `ai_log.py`. It reads `ai-sessions.log`, finds
unattributed sessions in the window, rewrites the log with `project=` keys
added.

## `backfill_window` function signature

```python
def backfill_window(
    project_dir: Path,
    start: datetime,
    end: datetime,
    project: str,
    *,
    dry_run: bool = False,
) -> int:
    """Attribute unattributed sessions in [start, end) to project.
    Returns the number of sessions attributed (or that would be, in dry_run)."""
```

Uses `_rewrite_lines_atomic` (already in `ai_log.py`) for safe writes.

## `halyard backfill` command

```
halyard backfill [--project <slug>] [--dry-run] [--confirm]
```

Algorithm:
1. Load all timeclock windows from `time.timeclock`.
2. For each unattributed session, find matching windows.
3. If exactly one match → attribute (or report in dry-run).
4. If zero matches → skip (no timeclock data for that period).
5. If multiple matches → skip silently (or prompt in `--confirm` mode).

In `--confirm` mode, ambiguous sessions are presented one by one with their
candidate projects; user picks one or skips.

## Log rewrite format

Attribution is added as a `project=` key on the existing `s` line:

Before: `s 2026-05-08T10:00:00 2026-05-08T10:45:00 claude-code claude-sonnet-4-5 ...`
After:  `s 2026-05-08T10:00:00 2026-05-08T10:45:00 claude-code claude-sonnet-4-5 ... project=acme:auth-migration`

This is the same format `assign_unattributed_sessions` uses today.
