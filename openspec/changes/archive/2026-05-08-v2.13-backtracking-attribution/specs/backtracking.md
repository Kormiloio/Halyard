# Spec: Backtracking Attribution

## `backfill_window` (ai_log.py)

```python
def backfill_window(
    project_dir: Path,
    start: datetime,
    end: datetime,
    project: str,
    *,
    dry_run: bool = False,
) -> int
```

- Reads `ai-sessions.log` from `project_dir`.
- Finds lines starting with `s ` where `session.start >= start` and
  `session.start < end` and `project=` is not already present.
- In dry_run mode: returns count without writing.
- Otherwise: rewrites log atomically with `project=<slug>` appended to each
  matched line.
- Returns number of sessions attributed.

## Stop command integration

After the `o` line is written and `~/.halyard/active` is removed:

```python
window_start, window_end = _last_closed_window(timeclock, account)
if window_start and window_end:
    count = backfill_window(project_dir, window_start, window_end, account)
    if count:
        console.print(f"  Attributed {count} AI session(s) to {account}.")
```

`_last_closed_window(timeclock_path, account)` reads the timeclock and returns
the (start, end) of the most recent closed window for that account slug.

## `halyard backfill` command

Located in `cli.py`.

```
halyard backfill [--project <slug>] [--dry-run] [--confirm]
```

- Requires a Halyard project in the current directory.
- `--dry-run` prints a table of sessions that would be attributed without
  writing.
- `--confirm` enables interactive mode for ambiguous sessions.
- Without `--confirm`, ambiguous sessions (overlapping windows) are silently
  skipped and reported in the summary.

## Overlap rule

A session is ambiguous if two or more distinct timeclock windows for different
projects both contain `session.start`. The session is skipped in batch mode.
