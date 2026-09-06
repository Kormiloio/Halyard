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


---

## Implementation notes (amending this design)

Two corrections, both found because the guard fired on its own change.

### The isolation had to be session-scoped

The design assumed a function-scoped autouse fixture was enough. It is not.
`monkeypatch` restores at each test's teardown, and `HubServer` runs in a
background thread that can outlive it — a write landing in that window hits
the *real* path after the patch is gone.

That race is order-dependent, which is why a full run looked clean
(474 → 474 rows) and the next run under a different `pytest-randomly` seed
leaked `tool-1`, `tool-2` and `t`. Verifying once was not enough to
establish the fix; two consecutive runs under different seeds were.

Holding the override for the whole session removes the window instead of
narrowing it.

### The guard compares tool names, not row counts

The design proposed counting rows on the reasoning that "no real tool writes
the sessions table during a test run — it is populated by an explicit
`halyard db sync`". That is wrong. The developer's own Claude Code hook
captures and syncs their work *while the suite runs*: the first guarded run
failed on 416 → 418 with a legitimate `claude-code` row among the leaked
fixtures.

A guard that fails on real usage is worse than no guard, because it gets
disabled rather than fixed. Comparing the set of tool names discriminates
correctly: real activity adds rows under tools already present, while a test
introduces a name that was not there.

This is the same reasoning the design already applied to reject watching the
whole `~/.halyard` directory — it just had not been carried far enough.
