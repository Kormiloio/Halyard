# v2.34 — Presence-Aware Human Timer

## Problem

The current human time display is misleading in two ways:

1. **"0m today" when the user worked for hours.** The auto-timer (v2.28) only
   writes timeclock entries when Claude Code hooks fire. It does not know about
   time spent reading AI output, implementing suggestions in VS Code, working in
   Codex, or using Gemini CLI. A developer who spent 6 hours in AI tools today
   sees "0m" unless they manually clicked Start/Stop.

2. **Manual Start/Stop is abandoned quickly.** Requiring users to remember to
   clock in and out is too much friction. It is the same reason physical
   timesheets fail. If the number reads "0m" despite hours of real work, the
   user stops trusting the tool.

The human time number is the most visible metric on The Bridge. If it is wrong,
everything else feels unreliable.

## Proposed model

**Presence windows, not clock-in/clock-out.**

A presence window is any period where the user was actively engaged with AI
tooling. Halyard infers presence from signals it already has:

| Signal | Source | Confidence |
|---|---|---|
| Claude Code hook fires | cc-session start/stop | High |
| Cursor hook fires | cursor-session start/stop | High |
| Gemini CLI hook fires | gc-session start/stop | High |
| VS Code extension active editing | vscode-extension heartbeat | Medium |
| Manual `halyard start` / `halyard stop` | timeclock | High (wins over auto) |

### Aggregation rules

1. Collect all AI session windows (start → end) across all tools for the day.
2. Collect all VS Code active editing windows from the extension heartbeats.
3. Merge overlapping windows with a configurable **idle gap** (default: 30 min,
   same as v2.28). Gaps shorter than the idle threshold are filled; gaps longer
   start a new presence block.
4. Sum the merged windows → "presence time" for the day.
5. Manual timeclock entries always override auto-detected windows for the same
   period.

### Display

The dashboard shows two numbers:

- **Human time — Xh Ym** (main metric) — merged presence window total
- **sub-label** — "auto-detected" if no manual timer was used; "manual" if
  `halyard start`/`halyard stop` was used; "mixed" if both contributed

This is honest: the user sees what was inferred and how. It does not claim
precision it doesn't have. A developer who ran 4 Claude sessions and edited in
VS Code will see a plausible number like "3h 40m auto-detected" rather than "0m".

### What changes

- `build_human_time_report()` gains a `presence_minutes` field derived from
  merged AI session windows.
- The dashboard's "Human Time" card uses `presence_minutes` when
  `timeclock_minutes` is zero.
- A new sub-label distinguishes auto-detected from manual time.
- The `time.timeclock` file remains the source of truth for manual entries.
  Auto-detected windows are never written to `time.timeclock` (they are
  ephemeral, computed on read). This preserves the append-only guarantee.

### What this is not

- Not a keylogger or activity tracker. Presence is inferred from AI session
  windows only — no screen activity, no keystrokes.
- Not a replacement for manual timers. Manual always wins.
- Not written to `time.timeclock`. Presence is a read-time computation.

## Success criteria

- A developer with 4 Claude Code sessions totalling 5 hours today sees "> 0m"
  without ever running `halyard start`.
- The sub-label distinguishes auto-detected from manual.
- Manual timeclock entries still display correctly and take precedence.
- No new data written to any file during auto-detection.
