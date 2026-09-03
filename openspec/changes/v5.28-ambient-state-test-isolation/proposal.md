# v5.28 — Ambient-state test isolation

## Why

Two test failures, both from the same root cause as v5.14 — tests coupled to
ambient machine state rather than to fixtures they control. v5.14 covered
one axis (the wall clock, via hard-coded May 2026 dates). This change covers
the two axes it did not: **calendar-day arithmetic** and **the real home
directory**.

Both were latent. Neither is a production defect.

### 1. Day-field underflow — breaks CI on the 1st and 2nd of every month

`tests/test_usage_dashboard_controls.py::_seed_sessions` built its
back-dated fixture rows by decrementing the day *field*:

```python
start = now.replace(hour=hour, minute=0, second=0).replace(day=now.day - day_offset)
```

With `day_offset` running 0..2, any run on the 1st, 2nd, or 3rd of a month
computes `day=0` or lower and raises:

```
ValueError: day is out of range for month
```

This is not theoretical. It took down `lint-and-test` on every open PR on
2026-09-02 — including PR #13 (v5.24 Antigravity) and PR #15 (v5.27
catch-up deadlock), whose own branches are level with `main` and otherwise
sound. `main`'s last CI run was 2026-07-09 and was green; it had not been
re-run since, so `main` was latently red as well.

Two things about that window are worth recording, because both misled the
first diagnosis of this bug:

- **It is the 1st and 2nd, not the 1st–3rd.** `day_offset` reaches 2, so
  the call raises when `now.day - 2 < 1`, i.e. `now.day < 3`. On the 3rd it
  computes day 1 and succeeds.
- **It closed mid-investigation.** UTC rolled to 2026-09-03 while this
  change was in review, and the failure stopped reproducing on its own.
  A branch *without* this fix now passes `lint-and-test`, which makes the
  green tick meaningless as evidence either way until the next 1st.

That self-healing is exactly why the bug survived: for roughly 29 days a
month the suite is green, and the two days it is not are the two days
nobody re-runs July's CI.

It also did **not** account for the whole red matrix. `lint-and-test (3.11)`
was independently red on `pip-audit` (setuptools 79.0.1, PYSEC-2026-3447) —
a separate failure this change does not address, fixed in a companion CI
commit.

Sibling `.replace(day=1, …)` calls in `tests/test_report.py` and
`src/halyard/dashboard.py` are safe — day 1 always exists — so this is the
only site.

### 2. Real `$HOME` leakage — breaks on any machine with Copilot history

`tests/test_v252_tool_detection.py::test_absent_tool_no_nudge` patches
`Path.home()` to `tmp_path`, stubs the Codex collector, then asserts that
`build_doctor_report(tool="all")` emits no `unwired.*` check when nothing is
on `PATH`. It gets `unwired.copilot`, because the Copilot collector's paths
are module-level constants:

```python
# src/halyard/collectors/copilot.py:20-21
_VSCODE_STORAGE_DIR = Path.home() / "Library/Application Support/Code/User/workspaceStorage"
_IMPORTED_STATE_FILE = Path.home() / ".halyard" / "copilot-imported"
```

They bind the *real* home at import time; patching `Path.home` afterwards
cannot reach them. So `copilot_history_present()` reads the developer's
actual VS Code storage, finds real `chatSessions/*.jsonl`, and fires the
nudge.

Green on CI (no VS Code there) and green when the file runs alone — that
isolation pass is an accident of import order. `_unwired_tool_checks`
imports the collector lazily, inside the function body, so running the file
alone binds the constants while `Path.home` is still patched. In the full
suite an earlier module has already imported it against the real home.

Observed locally: 1,769 passing + 1 failing.

## What

**Test-only. No production changes.**

1. `tests/test_usage_dashboard_controls.py` — subtract whole days with
   `timedelta(days=day_offset)` instead of decrementing the day field, and
   pin `microsecond=0` alongside the other truncations.
2. `tests/test_v252_tool_detection.py` — stub `copilot_history_present` /
   `copilot_imported_any` to `False` in the autouse `_fake_home` fixture,
   next to the Codex stubs already there.

## Out of scope

- **The wider `Path.home()` class.** Roughly twenty module-level
  `Path.home()` constants exist across `src/halyard/` (`db.py:31`,
  `registry.py:14`, `auto_timer.py:26`, `collectors/claude_code.py:123`,
  `collectors/codex_app.py:25`, and others). Each is immune to `Path.home`
  patching, so *any* test relying on that patch alone is latently coupled
  to the developer's real home. Only the Copilot instance fails today; the
  rest are dormant. The durable fix is a suite-wide guard — an autouse
  `conftest.py` fixture that repoints them, or a check that fails loudly
  when a test touches real `$HOME` — and it is deliberately deferred as a
  much wider diff than this branch should carry.
- Making the collectors resolve their paths lazily. That fixes the class
  properly, but it is a production change touching every collector and is
  not needed to make these tests correct.
- The `vscode-extension` CI job, which fails independently on 2
  high-severity npm advisories under `node_modules/postcss`. Same-colour
  symptom, unrelated cause; it needs its own lockfile bump.
