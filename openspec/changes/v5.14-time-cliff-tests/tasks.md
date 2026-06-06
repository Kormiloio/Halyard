# v5.14 — Tasks

## Phase 0 — Reproduce

- [x] Confirm baseline: `uv run pytest --no-header 2>&1 | tail -3`
      reports `41 failed, 1504 passed` (the 1504 includes v5.13's new
      tests).

## Phase 1 — Dev dependency

- [x] Add `freezegun>=1.5` to `[project.optional-dependencies].dev` in
      `pyproject.toml`.
- [x] `uv sync --extra dev` so the lockfile picks it up.

## Phase 2 — Apply autouse freeze fixture

Add the module-level autouse fixture to each file:

```python
import pytest
from freezegun import freeze_time

@pytest.fixture(autouse=True)
def _freeze_to_may_2026():
    with freeze_time("2026-05-15 12:00:00"):
        yield
```

- [x] `tests/test_dashboard.py`
- [x] `tests/test_dashboard_health_detail.py`
- [x] `tests/test_dashboard_layout.py`
- [x] `tests/test_integration_ledger.py`
- [x] `tests/test_outcome_sync.py`
- [x] `tests/test_tui.py`
- [x] `tests/test_v264_stats_graphs_parity.py`
- [x] `tests/test_v273_table_sort.py`
- [x] `tests/test_v57_dashboard_b_plus.py`

## Phase 2.5 — Production unblock (scope expansion)

- [x] `DashboardState.generated_at` in `src/halyard/reports.py`:
      rewrite `field(default_factory=datetime.now)` →
      `field(default_factory=lambda: datetime.now())`. The bare
      reference binds `datetime.now` at dataclass-definition time and
      slips past `freeze_time`; the lambda re-resolves on every call.
      Semantic no-op for production, unblocks the freezegun pin.
      Proposal amended to document this scope addition.

## Phase 3 — Verify

- [x] `uv run pytest --no-header 2>&1 | tail -3` → `0 failed`.
- [x] `uv run ruff check .` clean.
- [x] `uv run ruff format --check .` clean.
- [x] `uv run mypy src/` clean.

## Phase 4 — Document

- [x] Add v5.14 roadmap entry to `openspec/project.md`.
- [x] Tick every task in this file.

## Phase 5 — Correction (found during pre-release code review)

The Phase 3 "0 failed" tick was WRONG: the autouse freeze to 2026-05-15
broke `test_dashboard.py::test_render_dashboard_wake_month_param_scopes_panel`.
That test asserts the `wake_month="2026-05"` view shows a `rel="next"` link
"because we're in the past relative to now" — but pinning now to mid-May made
May the *current* month, correctly suppressing the next link, so the
assertion failed. The proposal's "Out of scope" claim that this test "does
not depend on `datetime.now()` for the May-2026 case" was incorrect — it
depends on now being *later* than May.

- [x] Re-freeze that single test to `2026-06-15` via an inner `@freeze_time`
      decorator (innermost wins over the module autouse fixture), restoring
      the now=June semantics it was written for. Verified passing.
- [x] Correct the "Out of scope" paragraph in `proposal.md`.
- [x] Re-run the full suite (excl. test_tui.py's sandbox-hanging Textual
      pilot tests) → 1614 passed, 0 failed (run with the v5.16–v5.18 batch).
- [x] Extended the fix to a 10th time-cliff file the gate surfaced:
      `tests/test_v54_dashboard_templating.py` (May-2026 session +
      `render_dashboard`, no clock injection) got the same
      `_freeze_to_may_2026` autouse fixture. This is the "separate additive
      ticket" the original proposal anticipated, folded in here.

## Phase 6 — TUI hang correction (owner code review, 2026-06-05)

- [x] The `test_tui.py` autouse freeze used a HARD freeze, which also freezes
      `time.monotonic` and starves the asyncio/Textual event loop the pilot
      tests (`app.run_test()`) drive — their timers never fire, so the suite
      hung (previously misattributed to "sandbox environment only" and worked
      around with `--ignore=tests/test_tui.py`). Fixed by switching that
      module's fixture to `freeze_time("2026-05-15 12:00:00", tick=True)`:
      the clock advances in real time from the frozen instant, so "today"
      stays 2026-05-15 (month filter satisfied) while `monotonic` moves and
      the loop runs. **`tests/test_tui.py` now passes in full — the
      `--ignore` workaround is no longer needed and the suite is releasable.**
