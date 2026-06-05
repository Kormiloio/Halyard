# v5.14 — Time-cliff test fix

## Why

41 tests across 9 test files break the moment the system clock crosses out
of May 2026. They have nothing to do with any recent change — they have
been latent on `main` since the May session-window assumptions were baked
in, and they bit us on June 2 when the calendar rolled over (1,503 passing
+ 41 failing on `main` at `f9c92bc`).

Root cause: tests in
`tests/test_dashboard.py`, `tests/test_dashboard_health_detail.py`,
`tests/test_dashboard_layout.py`, `tests/test_integration_ledger.py`,
`tests/test_outcome_sync.py`, `tests/test_tui.py`,
`tests/test_v264_stats_graphs_parity.py`, `tests/test_v273_table_sort.py`,
and `tests/test_v57_dashboard_b_plus.py` create `AiSession` objects with
hard-coded `datetime(2026, 5, …)` start/end dates, then call
`render_dashboard(tmp_path)` or `build_ai_report(tmp_path)`. The chokepoint
in `src/halyard/reports.py` (`build_ai_report`, lines 133–144) filters
sessions to `clock.year == start.year and clock.month == start.month`
where `clock = now or datetime.now()`. On any date outside May 2026 the
test data vanishes from `report.sessions` and downstream assertions fail.

This is purely a test-suite fragility issue. Production code is correct
(the "current month" semantic is the intended behaviour of the dashboard
and CLI report). The fix belongs in the tests.

## What

Pin the wall clock to a stable in-window timestamp for every test module
whose May 2026 fixtures depend on it. Use `freezegun.freeze_time` via an
autouse fixture scoped per-module — no plugin requirement, no marker
gymnastics, no production code changes.

Concretely:

- Add `freezegun>=1.5` to `[project.optional-dependencies].dev` in
  `pyproject.toml`.
- In each of the 9 affected test files, add a module-level autouse
  fixture that wraps every test in `freeze_time("2026-05-15 12:00:00")`.
- One surgical production tweak in `src/halyard/reports.py`:
  `DashboardState.generated_at` is changed from
  `field(default_factory=datetime.now)` to
  `field(default_factory=lambda: datetime.now())`. The bare reference
  binds `datetime.now` at dataclass-definition time, before any
  `freeze_time` monkey-patch can take effect; the lambda re-resolves on
  every call. This is a semantic no-op for production (the value
  written is the same `datetime.now()` it always was) and is the
  smallest change that lets the freezegun pin actually reach the field.
  No other source code, no test fixture data, and no new test files.

The frozen date (May 15) sits comfortably in the middle of the May 2026
window the existing fixtures already use, so neither edge of the month is
nudged into June or April.

## Out of scope

- Refactoring `build_ai_report` to accept a mandatory `now=` argument.
  Production already accepts it; threading it through every test call
  would be a wider, riskier diff than freezing the clock.
- Auditing other test modules that *might* harbour the same latent
  fragility. The verification gate for this change is "0 failures on a
  date past May 2026"; if a later month uncovers more, that is a
  separate, additive ticket.
- ~~Touching test_dashboard.py's `test_render_dashboard_wake_month_…`
  (v5.13) — its own param-driven date logic is correct and does not
  depend on `datetime.now()` for the May-2026 case it asserts.~~
  **CORRECTION (pre-release review, 2026-06-05):** this was wrong. That
  test asserts the `wake_month="2026-05"` view shows a `rel="next"` link
  *because May is in the past relative to now* — so it DOES depend on
  `datetime.now()` being later than May. The module autouse freeze to
  2026-05-15 made May the current month and suppressed the next link,
  failing the test. Fixed by re-freezing that one test to 2026-06-15 via
  an inner `@freeze_time` decorator (see tasks.md Phase 5).
