# PRD: Halyard Local Activity Dashboard

**Status — May 8, 2026:**
Implemented local surface; maintain and harden. This PRD describes the Glass
Cockpit/local dashboard direction. It remains part of the OSS core, but hosted
or team dashboards are deferred until the local ledger, security posture, and
design-partner demand are stronger. See
[`current-direction.md`](current-direction.md) for the current sequence.

---

## Summary

Halyard should include a local web dashboard, similar in spirit to the
Claude-mem local view, that shows what Halyard is capturing and calculating
while AI-assisted work is happening.

The dashboard is not the source of truth. It is a local read/write interface
over the same plain-text files: `time.timeclock`, `ai-sessions.log`,
`ai-plans.toml`, clients, projects, and invoices.

## Why

The AI Work Ledger is powerful, but raw logs can feel invisible. Users need a
way to see:

- Is Halyard running?
- Is my timer active?
- Did the Claude Code hook capture the session?
- Which project did the AI work get attributed to?
- What models and tools have been used today?
- How much has this client/project consumed so far?
- Which sessions are unattributed or need review?
- What evidence will go into the invoice?

Claude-mem's local dashboard works because it makes background memory activity
legible. Halyard needs the same kind of confidence-building surface for AI work
capture.

## Product Thesis

If Halyard is the ledger, the local dashboard is the instrument panel.

The CLI should remain the fastest workflow, but the dashboard should make the
system understandable at a glance. It should answer "what is going on right
now?" without requiring the user to inspect multiple files.

The design target is a modern "Glass Cockpit": calm, high-density, live, and
operational. It should feel like a professional instrument panel for AI work,
not a generic SaaS admin page.

## Goals

- Show live human and AI work capture in one place.
- Build trust that hooks and collectors are working.
- Surface attribution gaps before invoice time.
- Provide a local-first visual report for current day, project, and month.
- Let users inspect invoice evidence without exposing sensitive prompts or
  code contents.
- Keep all data local unless the user later opts into sync.

## Non-Goals

- Replace the CLI.
- Require a hosted service.
- Become the enterprise dashboard.
- Store a separate database as source of truth.
- Display private prompt or code content by default.

## Primary Views

### Glass Cockpit

The first screen is the operational cockpit. It combines active timer state,
AI capture status, today's spend, model mix, project attribution, and warnings
into one scannable surface.

It should use:

- compact metric tiles for human time, AI sessions, tokens, and cost;
- a live session stream for recent AI work;
- status indicators for hooks, logs, pricing, and attribution health;
- restrained charts for model/tool mix and cost over time;
- clear visual labels for captured, calculated, allocated, inferred, and
  missing values;
- a layout that works during real work, not just in a demo.

### Today

Shows the active timer, current project, recent AI sessions, token totals,
model mix, direct AI cost, allocated plan cost, and any capture warnings.

### Projects

Shows each client/project with human hours, AI sessions, AI cost, model mix,
and invoice readiness.

### Sessions

Shows the raw AI session stream from `ai-sessions.log`, with filters for date,
project, tool, model, source, and attribution state.

### Costs

Shows direct API spend, credits, seat allocation, plan configuration status,
and uncertainty labels.

### Invoice Evidence

Shows the client-safe evidence that would be attached to an invoice: tools,
models, sessions, token totals, costs, and trust labels.

### Health

Shows collector and environment status:

- Halyard project detected;
- Claude Code hook installed;
- active timer state;
- latest session captured;
- `ai-sessions.log` writable;
- known pricing table version;
- unattributed session count.

## UX Principles

- Local URL, local data, local trust.
- Read-only by default; writes require explicit confirmation.
- Fast refresh without needing a heavyweight frontend stack at first.
- Designed for confidence and inspection, not vanity analytics.
- Modern operational UI: crisp typography, restrained color, dense tables,
  compact metrics, and clear live status.
- Avoid marketing-page patterns. No hero splash, decorative gradients, or
  oversized cards in the working interface.
- Use color sparingly and semantically: green for healthy capture, amber for
  inferred or needs-review states, red for broken capture or missing files,
  neutral for normal historical data.
- Prefer familiar controls: tabs for views, filters for sessions, toggles for
  cost layers, and concise icon/status indicators for health.
- Keep text legible and layouts stable on laptop and desktop screens.
- No prompt/code transcript display unless the user opts into a future content
  capture feature.
- Clear status language: captured, calculated, allocated, inferred, missing.

## MVP Scope

The first dashboard should be started with:

```bash
halyard dashboard
```

It should bind to localhost, pick an available port, print the URL, and open a
browser only if the user passes `--open`.

MVP views:

- Glass Cockpit overview;
- Today summary;
- recent AI sessions;
- project cost table;
- unattributed sessions;
- collector health.

MVP data sources:

- `time.timeclock`;
- `ai-sessions.log`;
- `ai-plans.toml` when present;
- `halyard.toml`;
- `clients.toml`;
- `projects.toml`;
- selected files under `~/.halyard/` for state only.

## Later Scope

- Live updates through server-sent events or WebSockets.
- Attribution correction workflow.
- Invoice preview and appendix generation.
- Exportable charts.
- Team sync mode after design-partner validation.
- Hosted dashboard backed by the same local file protocol, after security and
  enterprise-readiness work.

## Success Metrics

- A user can run `halyard dashboard` and understand today's human plus AI work
  within 10 seconds.
- A user can tell at a glance whether capture is healthy, degraded, or broken.
- The dashboard clearly shows whether capture is healthy.
- Unattributed sessions are visible before invoice generation.
- The dashboard uses the same report calculations as the CLI.
- The dashboard never becomes required for the core local CLI workflow.

## Moat surface (v2.66) — ranks above commodity parity

The dashboard's commodity stats (tokens, streaks, models — the v2.64
parity floor) match what any single-tool dashboard shows. The **moat
surface** shows what none of them can, because none have a project,
client, dollar, attribution provenance, or outcome:

- **Billable evidence per client project** — human time + AI cost +
  outcome split (shipped/in-flight/abandoned via `pr_state`) +
  attribution confidence chip.
- **Cost by client** — spend, not tokens, per client project.
- **Leakage funnel** — adrift $ per remote, each with its exact
  `halyard link-repo` fix (proposed, never run).

These panels render **above** the commodity Usage panel by default and
that ordering is enforced by an executable test: parity is the price
of admission; the moat is the reason to stay, and is never demoted to
make room for vanity stats.
