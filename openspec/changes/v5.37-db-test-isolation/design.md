# v5.37 — Design

## Why a fixture rather than lazy resolution

The root cause is that `_DB_PATH` binds `Path.home()` at import. Resolving
it lazily — a `_db_path()` function called at each use — fixes it properly
and would fix the other twenty constants the same way.

Not done here. That is a production change across every module that owns a
path, made to fix a defect that only manifests in tests, and each call site
needs checking for the assumption that the path is stable within a process.
The conftest fixture is the proportionate fix, and it matches four existing
fixtures doing exactly this for the registry, the logs, the auto-timer and
the hub pointer.

What was missing is not another patched constant — it is anything that
notices when a new one appears.

## The guard counts rows, not files

The obvious guard watches `~/.halyard` for modification during a test run.
It cannot work here: a live Claude Code hook writes to that directory
continuously on the developer's own machine, so the watcher would fire on
legitimate activity and be disabled within a day.

Counting rows in `cache.db`'s `sessions` table is precise instead. No real
tool writes that table during a test run — it is populated by an explicit
`halyard db sync` — so a change means a test wrote it. Session-scoped, so
the cost is one query at each end rather than per test.

The connection is read-only (`mode=ro`) so the guard cannot itself become a
writer, and every `sqlite3.Error` degrades to `None`, which disables the
check rather than failing a run for an unrelated reason. A guard that breaks
the suite on a missing or locked database would be removed, not fixed.

## Why the $0.00 result is right

After deleting the 62 fixture rows the cache reports `$0.00` total cost.
That is correct: every real session in it is credits or subscription-billed
and records zero. The `$0.61` that vanished was invented entirely by tests,
which is what makes this worth more than tidiness — a spend total read off
that table was reporting fabricated money.
