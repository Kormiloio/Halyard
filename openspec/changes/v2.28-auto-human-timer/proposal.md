# Proposal: v2.28 — Auto Human Timer

## Why this change

The manual `halyard timer start` / `halyard timer stop` workflow requires the
developer to remember to clock in and out. In practice, when you are deep in a
Claude Code session, you do not think about the timer — so human time goes
unrecorded even though the AI time is captured perfectly.

Claude Code hooks already fire at session start (`UserPromptSubmit`) and session
stop (`Stop`). The developer is provably present during those windows. We should
use that signal to write timeclock entries automatically, without requiring any
manual action.

## Design

### Presence model, not per-session model

A single conversation with Claude Code fires many Stop hooks (one per turn or
sub-agent). Writing one `i`/`o` timeclock pair per hook would produce hundreds
of 30-second entries. Instead, the auto-timer uses a **presence window**:

- Session start → if no manual timer is running, open an auto-timer and write
  `i` to the timeclock.
- Each session start/stop → update a "last-activity" timestamp.
- Next session start → if last-activity was > 30 minutes ago, close the open
  auto-timer with `o` at the last-activity time, then open a new one.
- `halyard timer stop` → closes any open auto-timer as well as manual timers.

This produces one timeclock block per contiguous work session regardless of how
many AI turns it contained.

### State file

`~/.halyard/auto-timer` stores:

```
project=kormilo:halyard
started=2026-05-09 14:23:00
last_activity=2026-05-09 15:47:00
```

### Manual timer takes priority

If `halyard timer start` is running (i.e. `~/.halyard/active` exists), the
auto-timer does not start and does not write to the timeclock. Manual always
wins.

### Attribution

Uses the same attribution priority as AI sessions:
1. Active manual timer project (but if manual is running, auto-timer is idle)
2. `git remote` inference via `infer_project(cwd)`
3. Falls back to `unattributed` — written to timeclock as `unattributed`

### Timeclock entries

Auto-timer entries are written with a `;auto` comment so they can be
distinguished from manual entries:

```
i 2026-05-09 14:23:00 kormilo:halyard  ;auto
o 2026-05-09 15:47:00
```

### Inactivity window

Default: 30 minutes. Not user-configurable in v2.28 (deferred to v2.29 if
there's pull).

## Files changed

- `src/halyard/collectors/claude_code.py` — call `auto_timer_activity()` on
  session start and `auto_timer_close_if_stale()` on session start (checks
  prior window before opening new one)
- `src/halyard/auto_timer.py` — new module: state management, timeclock writes
- `tests/test_auto_timer.py` — new test file

## What this does NOT do

- Does not modify the manual `halyard timer start / stop` workflow.
- Does not track time from Cursor, Gemini, or Codex hooks (can be added later).
- Does not start a timer if no Halyard project is found (cwd not under a
  project and no hub configured).
- Does not backfill historical AI sessions into the timeclock.

## Success criteria

- Working with Claude Code for 45 minutes produces one `i`/`o` pair covering
  that window, attributed to the correct project.
- A 45-minute gap between sessions produces two separate timeclock blocks.
- Running `halyard timer start` before a session suppresses the auto-timer for
  that window.
- `halyard timer stop` closes an open auto-timer.
- All existing timeclock and timer tests continue to pass.
