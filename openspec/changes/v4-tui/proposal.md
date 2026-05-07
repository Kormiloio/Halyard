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

## What the TUI does

`halyard tui` is a [Textual](https://textual.textualize.io/) application with:

- **Live session feed** — new sessions appear in real time as they are appended
  to the log, with tool icon, model, project, duration, and cost.
- **Project drill-down** — navigate to a project row and press Enter to expand:
  session history, model mix, daily spend chart, budget status.
- **Branch filter** — press `b` to open a branch selector showing all branches
  seen in the log; filter the feed to a single branch.
- **Budget status panel** — shows daily and monthly spend vs limits for all
  configured projects. Color-coded green → yellow → red → blinking red.
- **Model breakdown** — bar chart of token/cost distribution across models for
  the selected time window.
- **Time window** — `d` today, `w` week, `m` month, `a` all time.
- **Keyboard-first** — all navigation by keyboard. `?` opens the help panel.

## Design decisions (locked)

All five open questions from the proposal phase have been resolved:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Replace or supplement `halyard dashboard`? | **Supplement** — `halyard tui` is a new command; `halyard dashboard` unchanged | Rich table has users; CI/tmux/screen-reader contexts need it |
| Textual as a dependency? | **Optional extra** — `pip install halyard[tui]` | Keeps the base install lean; graceful error if not installed |
| State model? | **In-memory copy with file watcher** | 10k sessions ≈ a few MB; don't overengineer until memory is a complaint |
| Write actions? | **Read-only for v4** | Textual forms are expensive to build correctly; `assign-unattributed` CLI covers writes |
| Session scope? | **Hub view by default, `p` to filter to current project** | Hub view is never empty; filtering down is natural |

## What this change does NOT do

- No agent or AI integration in the TUI. `halyard log` is the AI command; the
  TUI is a display and navigation layer only.
- No write actions (assigning sessions, editing tags, starting/stopping timers).
  All writes go through dedicated CLI commands.
- No browser-based UI. Terminal-only.
- No multi-user or networked view. Local data, local display.
- No replacement of `halyard dashboard`. Both commands exist.

## Success criteria

- `halyard tui` launches in an interactive terminal and shows a live session feed.
- Sessions appended to the log appear in the feed within 1 second.
- Project drill-down and branch filter work with keyboard navigation alone.
- Budget status panel shows correct spend-vs-limit for all configured projects.
- `pip install halyard[tui]` installs the optional dependency.
- Running `halyard tui` without Textual installed prints a clear install instruction
  and exits 1.
- `halyard dashboard` continues to work unchanged.
- The TUI is covered by unit tests (mocked sessions, key dispatch).
