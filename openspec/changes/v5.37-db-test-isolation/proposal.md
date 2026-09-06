# v5.37 — The test suite wrote the developer's production database

## Why

The last deferred item from v5.28, and it was getting worse rather than
sitting still.

`db._DB_PATH` is a module-level constant bound to the real `Path.home()` at
import time, and `get_db()` uses it directly:

```python
db.py:31   _DB_PATH = Path.home() / ".halyard" / "cache.db"
db.py:209  conn = sqlite3.connect(str(_DB_PATH))
```

A test patching `Path.home` never reaches it — the constant was resolved
when the module was imported. Only three tests patched `_DB_PATH`
explicitly; every other test touching the cache wrote into the developer's
production database.

Measured on the machine that found it: **62 of 474 rows** were test
fixtures — `tool-1`, `tool-2`, `test-tool`, `slow-hub-tool`, `shell-tool`,
`external-tool`, `t` — carrying **$0.61 of fabricated cost**. The count was
38 earlier the same day and grew with each suite run.

The cost figure is the sharp end. Every real session in that cache records
`cost_usd = 0.00` (they are credits/subscription). So the *only* money in
the table was invented by tests, and any spend total derived from it was
entirely fiction.

This is the same class as the v5.23 follow-up that added
`_no_real_hub_pointer`, when v5.21 test rows were found written into the
developer's real hub ledger.

## What

- **`_isolate_db`** — an autouse fixture pointing `db._DB_PATH` at a temp
  path, matching the existing `_isolate_registry`, `_isolate_halyard_logs`
  and `_no_real_hub_pointer` fixtures. `db` was simply missing from that
  list.
- **`_guard_real_cache_db`** — a session-scoped fixture that counts rows in
  the real cache before and after the run and fails if they changed. This is
  the part that catches the *next* one: roughly twenty module-level
  `Path.home()` constants across `src/halyard/` have the same shape
  (`registry.py`, `budget.py`, `pricing.py`, `attribution.py`,
  `state_integrity.py`, the collectors), and enumerating them one incident
  at a time is how this survived.

Verified: real cache.db held 474 rows before a full suite run and 474 after,
with all 1918 tests passing. The 62 fixture rows were then deleted from the
maintainer's database after a backup, leaving 412 real rows and $0.00 —
which is correct, not a loss.

## Out of scope

- **Making the ~20 constants resolve lazily.** That is the durable fix and
  removes the whole class, but it is a production change touching every
  module that owns a path, for a defect whose blast radius is tests. The
  guard makes the next instance loud and cheap to find, which is the part
  that was missing.
- Watching all of `~/.halyard` rather than one table. A live Claude Code
  hook writes there during a suite run, so a directory watcher would
  false-positive on legitimate activity — the guard counts rows in a table
  no real tool writes during tests.
