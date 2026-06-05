# v5.14 — Design

## Decision: freezegun, not a `now=` injection

Two viable shapes were considered before writing any code:

**Option A (chosen) — autouse `freeze_time` fixture per affected module.**
Pin `datetime.now()` to `2026-05-15 12:00:00` for the duration of every
test in the affected files. Production code untouched.

- Pros: smallest diff (one fixture block per file, 9 files, no production
  changes). Failures fixed without re-validating any shipping behaviour.
  Catches every clock site at once, including ones we haven't enumerated
  (e.g. nested helpers, presence calculations).
- Cons: introduces `freezegun` as a dev dependency. Requires touching 9
  test files mechanically.

**Option B (rejected) — thread `now=` through `render_dashboard` and
`build_dashboard_state`.** Add an optional `now: datetime | None` param
on `render_dashboard`, propagate to `build_dashboard_state` and onward
to `build_ai_report`, `_compute_presence_today`, `_detect_timer_collision`,
`build_health_checks`, etc.

- Pros: no new dependency.
- Cons: invasive (touches the public dashboard signature and every
  state-building helper); every failing test must also be edited to pass
  `now=`; doesn't fix sites we haven't found; expands the production
  API surface for a test-only need.

The user's brief explicitly prefers (a). The 41 failing tests prove the
failure surface is wide enough that a chokepoint-style fix (freeze the
clock once at the module boundary) is right; per-call `now=` plumbing
would be busywork that catches less.

## Why `freezegun` and not `time-machine`

Both are mature. `freezegun` is the more common dev dependency in the
Python ecosystem (used by Django/Mozilla/etc.) and its `freeze_time`
context manager is the cleanest fit for `@pytest.fixture(autouse=True)`
without needing a pytest plugin. `time-machine` has the edge on
performance (C-level), but the affected suite already runs in ~45s with
coverage on; this is not a hot loop.

## Fixture shape

Each affected test module gets:

```python
import pytest
from freezegun import freeze_time

@pytest.fixture(autouse=True)
def _freeze_to_may_2026():
    with freeze_time("2026-05-15 12:00:00"):
        yield
```

Module-scope, not session-scope. A session-scope autouse fixture in
`tests/conftest.py` would freeze the clock for the entire suite — fine
in theory, but it would silently mask any real time-dependent test that
hasn't shown its hand yet, and it would freeze tests that don't need it
(e.g. v5.12 portability tests that assert against the real OS clock for
file mtimes). Module-scope keeps the blast radius surgical.

The frozen instant — `2026-05-15 12:00:00` — sits roughly in the middle
of the May 2026 fixtures (which range from May 1 to May 14). It is well
clear of both month boundaries.

## Trust labels

The change is test-infrastructure-only. No `AiSession` data flow is
altered. `to_log_line` / `parse_sessions` are not touched. The dashboard
keeps rendering "current month" semantics in production exactly as before;
only the test wall clock is pinned.

## Trade-off accepted

`freezegun` patches `datetime.now()` and `time.time()` for the duration
of the context manager. A test that depends on the real system clock
inside a frozen-clock module (e.g. measuring elapsed wall time) would
silently misbehave. None of the 9 affected files currently do this; the
three `datetime.now()` call sites in `tests/test_tui.py` (lines 540,
569, 696) read "now" for setup data, not for timing assertions, so
freezing is fine.

## Rejected alternatives

- **Hard-code session dates to relative offsets from `datetime.now()`.**
  Forces a rewrite of every fixture and obscures the readable
  `datetime(2026, 5, 7, ...)` literal. Time-anchored assertions in the
  rendered HTML (e.g. "May 2026" in panel headings) would still need
  separate handling.
- **Move the "current month" filter behind a feature flag.** Bends
  production for a test problem. Production behaviour is correct.
- **Mark the failing tests `xfail` until June ends.** Doesn't fix the
  bug, just hides it; same failure recurs every month rollover.
