# v5.37 — Tasks

## Code

- [x] `_isolate_db` autouse fixture in `tests/conftest.py` pointing
      `db._DB_PATH` at a temp path. **Session-scoped** — a function-scoped
      patch is restored at each teardown, and a `HubServer` thread
      outliving it writes the real path in that window. Design amended.
- [x] `_guard_real_cache_db` session-scoped fixture: compare the *set of
      tool names* before and after. **Not a row count** — the developer's
      own Claude Code hook syncs during a run, so counting fails on
      legitimate activity. Design amended.
- [x] Read-only connection; any `sqlite3.Error` disables the check rather
      than failing the run.

## Verified

- [x] **Two consecutive full runs under different `pytest-randomly` seeds**
      introduced no new tool names. One clean run was not sufficient
      evidence: the leak is order-dependent, and the first verification
      (474 → 474) passed by luck before the next run leaked.
- [x] 1918 tests still pass.
- [x] 62 fixture rows deleted from the maintainer's database after a
      timestamped backup — 412 real rows remain, `$0.00` total cost, which
      is correct since every real session is credits/subscription.

## Gates

- [x] `uv run pytest`
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Out of scope (recorded)

- [ ] Making the ~20 module-level `Path.home()` constants resolve lazily —
      the durable fix for the whole class, but a production change touching
      every module that owns a path, for a defect whose blast radius is
      tests. The guard makes the next instance loud instead.
