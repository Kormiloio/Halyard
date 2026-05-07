# Proposal: v4 — Textual Interactive Terminal Dashboard

## Why this change

The current `halyard dashboard` is a Rich auto-refreshing table. It renders the
right data and updates live as sessions are appended to the log. But it is a
one-way display: you cannot navigate, filter, drill down, or act on what you see
without restarting the command with different flags.

Three AI tool evaluations of Halyard converged on the same gap: the daily-driver
UX is missing. A developer should be able to open a terminal, launch Halyard,
and see everything relevant to their current work — without composing CLI flags
from memory. Cursor described this as "daily driver loop." Antigravity (Gemini
CLI) specifically proposed a Textual TUI.

The Rich dashboard works. It is not going away for non-interactive contexts. The
TUI is the interactive layer that makes Halyard feel like an instrument panel
rather than a report generator.

## What a TUI would do

The TUI is a [Textual](https://textual.textualize.io/) application invoked by
`halyard tui`. It provides:

**Live session feed**
Sessions appear in real time as they are appended to the log. Each row shows
the tool icon, model, project, duration, token counts, and cost. New sessions
appear at the top with a brief highlight animation.

**Project drill-down**
Navigate to a project row and press Enter to expand it: session history,
model mix breakdown, daily spend chart, and budget status for that project.
Navigate back to the project list with Escape.

**Branch cost view**
Filter the session list to a specific git branch tag. Press `b` to open a
branch selector showing all branches seen in the log.

**Budget status panel**
A sidebar (or bottom panel) showing current daily and monthly spend vs limits
for all configured projects. Color-coded: green (under 50%), yellow (50–80%),
red (over 80%), blinking red (exceeded).

**Model breakdown**
Bar chart or sparkline showing token and cost distribution across models used
in the selected time window.

**Time window**
Switchable with keyboard shortcuts: `d` = today, `w` = this week, `m` = this
month, `a` = all time. The current window is shown in the header.

**Keyboard-first navigation**
All navigation by keyboard. No mouse required. `?` opens a help panel listing
all key bindings.

## Design decisions that must be resolved before writing specs

### 1. Replace or supplement `halyard dashboard`?

**Option A:** `halyard tui` is a new command. `halyard dashboard` stays as-is
for non-interactive contexts (CI, tmux with no mouse, screen readers, log
piping).

**Option B:** `halyard dashboard` becomes an alias for `halyard tui`. The old
Rich table is deprecated.

**Option C:** `halyard dashboard` auto-detects whether it's running in an
interactive terminal and launches the TUI if so, or falls back to the Rich
table if not (e.g., when stdout is not a tty).

Recommendation: Option A in v4. The Rich dashboard has users. Don't break it.
Option C is the long-term destination but requires reliable tty detection.

### 2. Textual as a dependency

Textual adds approximately 500KB to the install. Options:

**Option A:** Required dependency in `pyproject.toml`. Everyone gets the TUI.
Simple, but bloats the base install.

**Option B:** Optional extra — `pip install halyard[tui]`. Users who want the
TUI install it explicitly. The CLI gracefully errors with install instructions
if `textual` is not importable.

**Option C:** Separate package — `pip install halyard-tui`. Fully decoupled, but
adds a release coordination burden.

Recommendation: Option B. Keeps the base install lean. The install instruction
on error is one line.

### 3. Session data state model

**Option A:** In-memory copy of all sessions loaded at startup, updated by a
file watcher. Fast navigation, O(N) memory for large logs.

**Option B:** Re-read the log on every navigation action. Always up-to-date,
but may feel sluggish for large logs.

**Option C:** In-memory index (session timestamps, offsets) with lazy reads for
detail views. Best of both, more complex to implement.

Recommendation: Option A for v4. Most logs will be under 10,000 lines (~1MB).
Revisit if memory becomes a complaint.

### 4. Write actions in the TUI

Should the TUI allow any writes — assigning an unattributed session, editing a
project tag, starting/stopping a timer? Or read-only?

Recommendation: Read-only in v4. Write actions require confirmation UX that
is complex to build well in Textual. The `halyard assign-unattributed` CLI
command (from v2.4) covers the primary write need.

### 5. Session scope: single project or multi-project?

Should `halyard tui` show:
(a) Only sessions from the current project directory
(b) All sessions from the hub (global view)
(c) Either, switchable by key

Recommendation: Hub view by default, with a `p` key to filter to the current
project. The hub is where all sessions end up anyway.

## What this change does NOT do

- No agent or AI integration in the TUI itself. `halyard log` is the AI command.
  The TUI is a display and navigation layer only.
- No browser-based UI. The TUI is terminal-only.
- No multi-user or networked view. This is local data, local display.

## Next step

Mario to make calls on the five design decisions above. Once resolved, write
`specs/tui.md` and `design.md`, then open implementation.

## Success criteria (to be finalized after design decisions)

- `halyard tui` (or `halyard dashboard`) launches in an interactive terminal and
  shows a live session feed.
- Session feed updates within 1 second of a new line being appended to the log.
- Project drill-down works with keyboard navigation.
- Budget status panel shows correct spend-vs-limit for all configured projects.
- The TUI is installable via `pip install halyard[tui]`.
- Graceful error if `textual` is not installed: "Run `pip install halyard[tui]`
  to enable the interactive dashboard."
- `halyard dashboard` (Rich table) continues to work unchanged.
