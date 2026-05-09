# Spec: v4 — Textual Interactive Terminal Dashboard

## Launch and dependency

### WHEN the user runs `halyard tui` and `textual` is installed
THEN the TUI application launches in the current terminal, filling the
available screen with the main layout.

### WHEN the user runs `halyard tui` and `textual` is not installed
THEN the command prints:
`Textual is required for the interactive dashboard. Install it with:
  pip install halyard[tui]`
and exits with code 1. No crash, no stack trace.

### WHEN `halyard tui` is run inside a Halyard project directory
THEN the TUI loads the hub log if a hub is configured, otherwise the project's
`ai-sessions.log`. The active project is noted in the header.

### WHEN `halyard tui` is run outside any project directory and no hub is configured
THEN the TUI launches with an empty session feed and a header note:
`No project or hub found — run 'halyard init' or 'halyard set-hub'`

### WHEN the user presses `q` or `ctrl+c`
THEN the TUI exits cleanly and the terminal is restored.

---

## Main Layout

The TUI uses a main column plus a stacked side rail:

```
┌─────────────────────────────────────────────────────┐
│ HALYARD  [hub: ~/kormilo]  [May 2026]  [d w m a]    │  ← Header
├──────────────────────────┬──────────────────────────┤
│ Session Feed             │ Current Watch            │
│ Project Detail           ├──────────────────────────┤
│                          │ Captain's Quarters       │
│                          ├──────────────────────────┤
│                          │ Voyage Roster            │
│                          ├──────────────────────────┤
│                          │ Voyage Stats             │
│                          ├──────────────────────────┤
│                          │ Budget Status            │
│                          ├──────────────────────────┤
│                          │ Model Breakdown          │
├──────────────────────────┴──────────────────────────┤
│ ? help  d today  w week  m month  a all  p project  │  ← Footer
└─────────────────────────────────────────────────────┘
```

---

## Session feed

### WHEN a new line is appended to the active log file
THEN it appears at the top of the session feed within 1 second, highlighted
briefly before settling to normal styling.

### WHEN a session row is displayed
THEN it shows: tool icon, model (truncated to 20 chars), project slug, duration,
input+output token counts, and cost in USD.

### WHEN the session feed is in hub mode (default)
THEN sessions from all projects are shown, ordered by start time descending.

### WHEN the user presses `p`
THEN the feed toggles to show only sessions from the current project directory.
The header updates to show `[project: <slug>]`. Pressing `p` again returns to
hub view.

### WHEN the active time window is `today`
THEN only sessions with a start time on the current calendar day are shown.
The same applies to `week` (last 7 days), `month` (current calendar month),
and `all` (no time filter).

---

## Project drill-down

### WHEN the user navigates to a project row in the session feed and presses `Enter`
THEN the session feed is replaced with a project detail view showing:
- All sessions for that project in the current time window
- A per-model cost breakdown bar chart
- Today's spend and monthly spend vs budget limits (if configured)

### WHEN the user presses `Escape` from the project detail view
THEN the main session feed is restored.

---

## Branch filter

### WHEN the user presses `b`
THEN a modal overlay appears listing all branch names seen in `branch:` tags
in the active log, sorted by most recent session.

### WHEN the user selects a branch from the list
THEN the session feed filters to only sessions tagged with that branch.
The header shows `[branch: <name>]`.

### WHEN the user presses `b` again or `Escape`
THEN the branch filter is cleared and all sessions are shown again.

---

## Budget status panel

### WHEN the budget status panel is visible
THEN each configured project slug is shown with:
- Today's spend and daily limit (if set)
- Month-to-date spend and monthly limit (if set)
- A color indicator: green (under 50%), yellow (50–80%), red (80–100%),
  blinking red (over limit)

### WHEN no budgets are configured
THEN the budget panel shows: `No budgets set — run 'halyard set-budget'`

---

## Model breakdown panel

### WHEN the model breakdown panel is visible
THEN it shows a bar chart of cost by model for the active time window and
scope (hub or project). Each bar shows model name, session count, and
percentage of total cost.

---

## Current Watch Panel

### WHEN no timer is active for the current project directory
THEN the panel shows `At anchor`, total sessions, proof state, and either
`Manifest clean` or an SOS/adrift line for sessions without project attribution.

### WHEN a timer is active for the current project directory
THEN the panel shows `Making way · <slug>`, elapsed watch time, sessions since
the timer started, manifest coverage, proof state, cost, and an SOS/adrift line
when any current-watch sessions are unattributed.

---

## Captain's Quarters Panel

### WHEN the panel is visible
THEN it shows the user's current rank, progress toward the next rank, stripe
state, proof score, manifest coverage, Passport stamps by AI tool, and earned
medals.

### WHEN the TUI's session feed is filtered by time window, project scope, or branch
THEN Captain's Quarters still uses the full loaded log so ranks, medals, and
Passport stamps do not appear to disappear during navigation.

---

## Voyage Roster Panel

### WHEN the panel is visible
THEN it shows the Friends of the Sea project roster with stage labels,
session-count progress, moored counts, and completed-project creature traits
when available.

### WHEN the TUI's session feed is filtered by time window, project scope, or branch
THEN the Voyage Roster still uses the full loaded log so project voyage state
remains stable while the user explores filtered views.

---

## Time window

### WHEN the user presses `d`, `w`, `m`, or `a`
THEN the session feed, project drill-down, Voyage Stats panel, and model
breakdown update to reflect the new time window. Current Watch, Captain's
Quarters, and Voyage Roster continue to use the full loaded log.

---

## Keyboard reference

| Key | Action |
|-----|--------|
| `d` | Time window: today |
| `w` | Time window: this week |
| `m` | Time window: this month |
| `a` | Time window: all time |
| `p` | Toggle hub view / current project view |
| `b` | Open branch filter selector |
| `Enter` | Drill into selected project |
| `Escape` | Exit drill-down or close modal |
| `?` | Toggle help panel |
| `q` / `ctrl+c` | Quit |
