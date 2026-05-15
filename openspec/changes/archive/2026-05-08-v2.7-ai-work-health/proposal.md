# Proposal: v2.7 — AI Work Health

## Why this change

Halyard captures rich session metadata: tool calls, errors, wall time, code
delta, model breakdown. This data sits in `ai-sessions.log` but nothing
surfaces it as a coherent picture of how AI-assisted work is going.

The gap is the difference between a cost dashboard and a work intelligence
platform. Cost tells you what you spent. Work health tells you what the AI
was actually doing — and whether it was useful.

This change introduces `halyard health`: a local report that reads captured
metadata and surfaces five categories of signals. The report is careful:
these are observations, not scores. A high error rate means a session was
noisy, not that the developer did something wrong.

## What the report says

Five signal categories, each showing flagged sessions with context:

**High tool error rate** — sessions where errors exceeded 25% of tool calls
with at least 5 calls (small sessions excluded to avoid noise). Signals that
an agent was blocked, tool calls were failing, or the task was not well-suited
to agentic execution.

**Wall time ≫ active agent time** — sessions where elapsed wall time was
significantly longer than measured active agent time. Signals idle waiting,
blocked tool calls, or human-in-the-loop friction. Requires `agent_active_seconds`
to be populated; shown as unavailable for tools that do not expose it.

**High token spend, low code delta** — sessions with meaningful cost but
minimal code output (lines added plus removed below a threshold relative to
cost). Signals possible thrash: the model spent tokens without producing
durable work. Requires `code_added`/`code_removed` to be populated.

**Repeated sessions on same project and branch** — three or more sessions
hitting the same `project` + `branch` combination within a single calendar day.
Signals repeated attempts at the same task: the AI may be stuck, the task may
be underspecified, or the approach may need rethinking.

**Unattributed high-cost sessions** — sessions with no `project` attribution
and cost above the 75th percentile for the period. Signals missing capture
context: these sessions cost money but cannot be allocated to any client or
project.

## What the report does NOT do

- It does not compute a productivity score, efficiency rating, or AI quality
  index. There is no aggregate "health score."
- It does not write anything to `ai-sessions.log` or any project file.
- It does not compare developers to each other.
- It does not claim that any flagged signal is definitely a problem. The report
  says "here is what was observed." The developer decides what it means.

## Command

```bash
halyard health
halyard health --period today
halyard health --period week
halyard health --project acme:auth
halyard health --format json
```

Default period: month. Default scope: hub or project directory. JSON output
is structured for downstream processing or export.

## Success criteria

- `halyard health` runs offline with no API key required.
- All five signal categories are evaluated and shown when relevant data exists.
- Signal categories with insufficient data (e.g. no sessions with `code_added`)
  are shown as "No data — requires tool support."
- The report header states clearly that signals are observations, not scores.
- JSON output is stable and documented.
- The command is covered by unit tests for each signal detector.
