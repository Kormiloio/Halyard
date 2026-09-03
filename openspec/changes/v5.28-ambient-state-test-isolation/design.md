# v5.28 — Design

## Axis 1 — day arithmetic

`timedelta` is the fix, not a guard on `now.day`. Clamping (`max(1, now.day
- offset)`) would keep the call from raising but would silently collapse
three distinct fixture days into one on the 1st and 2nd, so the suite would
"pass" while testing something other than what it claims. Subtracting a
`timedelta` rolls into the previous month correctly and keeps three
distinct days in every case.

`microsecond=0` joins the existing `hour/minute/second` truncation because
the rows are serialised through `strftime('%Y-%m-%dT%H:%M:%S')`; leaving
microseconds live meant the in-memory value and the written line disagreed.
Harmless today, but it is the kind of drift that makes a later round-trip
assertion mysterious.

### Residual, accepted

On the 1st and 2nd of a month, `day_offset` 1 and 2 now land in the
*previous* month. `test_models_tab_renders_models_panel` asserts only that
`sonnet` and `gpt-4o` appear, and `day_offset=0` is always in the current
month, so the assertions hold regardless of how the dashboard's range
filter treats the older rows. Pinning the clock with `freeze_time` (the
v5.14 mechanism) would remove the ambiguity entirely, but this module was
deliberately moved *to* relative dates in `b471aee` precisely to get away
from a frozen date that fell out of the 30-day window. Re-freezing it would
undo that. Noted here so the next reader does not "fix" it back.

## Axis 2 — why patch the module attribute, not the constants

Two places to intervene:

1. **The constants** — `copilot._VSCODE_STORAGE_DIR` and
   `copilot._IMPORTED_STATE_FILE`, repointed at `tmp_path`.
2. **The functions** — `copilot.copilot_history_present` and
   `copilot.copilot_imported_any`, replaced with `lambda: False`.

Option 2 is chosen. `_unwired_tool_checks` resolves those names through the
module object at call time:

```python
# src/halyard/doctor.py:467
from halyard.collectors.copilot import copilot_history_present, copilot_imported_any
```

Because the import sits inside the function body, it re-executes on every
`build_doctor_report` call and reads whatever the module attribute currently
holds. A `monkeypatch.setattr` on the module therefore always wins, whether
or not the module was already imported against the real home. Option 1 works
too, but it couples the test to the collector's private path layout — and
this test is about the doctor's nudge logic, not about where Copilot stores
its chats. Option 2 also matches what the file already does for Codex two
lines earlier, so the fixture reads as one consistent idea.

## Why the fixture, not just the failing test

`test_absent_tool_no_nudge` is the only test asserting the *absence* of every
`unwired.*` id, so it is the only one failing. But four others
(`test_hooks_present_suppresses_nudge`, `test_mcp_only_suppresses_nudge`,
`test_scoped_run_only_that_tool`, `test_codex_already_imported_no_nudge`)
call `build_doctor_report(tool="all")` and make narrower absence assertions.
They pass only because they happen not to name `unwired.copilot`. Putting
the stub in the autouse fixture makes the module's baseline explicit — "no
Codex history, no Copilot history, nothing imported" — instead of leaving
four tests one assertion-widening away from the same failure.

`test_unwired_warnings_preserve_exit_code` asserts the nudge list is
non-empty; it puts `claude`, `cursor`, and `gemini` on `PATH`, so
suppressing Copilot does not empty it.

## Verification

Each axis needs a different check, and neither is the obvious one.

**Day underflow** reproduces only on the 1st and 2nd (`day_offset` reaches
2, so it raises when `now.day < 3`). On the 3rd–31st the suite is green with
or without the fix, so a green run outside that window is not evidence.

This bit during review: the original failure was observed on 2026-09-02,
UTC rolled to the 3rd before CI finished, and a branch *without* the fix
then passed `lint-and-test` cleanly. Do not read that as verification.
The honest local check is to force the date rather than wait for it:

```python
from datetime import datetime
for day in (1, 2, 3):
    now = datetime(2026, 9, day, 12, 0, 0)
    [now.replace(hour=9).replace(day=now.day - o) for o in range(3)]  # pre-fix form
```

Days 1 and 2 raise `ValueError`, day 3 does not.

**Home leakage** cannot be verified by running the file alone — it passed
before the fix. It needs the full suite on a machine with real Copilot
history present and `~/.halyard/copilot-imported` absent, which is the
state this repo's development machine is in:

```
ls ~/Library/Application\ Support/Code/User/workspaceStorage/*/chatSessions  # non-empty
ls ~/.halyard/copilot-imported                                              # absent
uv run pytest -q
```

Before: `1 failed, 1769 passed`. After: `1770 passed`.
