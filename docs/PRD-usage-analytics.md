# PRD: Halyard Usage Analytics

**Status - May 14, 2026:**
**Shipped — 36 of 39 openspec tasks complete; 3 remaining are user-only
visual review (layout verification, release screenshot, demo GIF).**

The shared aggregation service (`src/halyard/usage.py`), the dashboard
Usage Analytics panel with summary cards, activity heatmap, model and
tool breakdowns, the new Overview/Models tab split with range segmented
control (7d/30d/all), the daily-by-model SVG stacked bar chart with the
v2.23 colour palette, and the `halyard usage --range --json` CLI all
shipped in [v2.23-usage-analytics](../openspec/changes/v2.23-usage-analytics/).
README quickstart and troubleshooting both reference the new surface.

This PRD is now historical reference for the design intent rather than
forward-looking work. The Bridge remains the operational view for
capture, attribution, health, and billing readiness; Usage Analytics
makes the same ledger feel legible, memorable, and useful at a glance.

---

## Summary

Halyard should include a beautiful local usage analytics view that shows how a
developer or team uses AI tools over time: sessions, messages or interaction
counts where available, tokens, models, active days, streaks, peak hours, and
model share.

This is the "personal stats" layer over Halyard's AI work ledger. It should
make Halyard feel as immediately useful and satisfying as the best individual
tool dashboards, while preserving Halyard's stronger cross-tool, project,
cost, and evidence foundation.

## Why

Individual AI tools are starting to expose polished session analytics. These
views are useful because they answer simple questions quickly:

- How much did I use this tool?
- Which model did I rely on?
- When was I most active?
- How many days did I work with AI?
- Where did my token volume spike?
- What changed over the last 7 or 30 days?

Halyard already captures much of the underlying data, and captures it across
tools. Today, however, Halyard's main surfaces are operational: reports,
tables, cost allocation, budgets, health, attribution, and invoices. That is
valuable, but it does not yet create the quick "I understand my AI work at a
glance" moment.

Usage Analytics should close that gap without turning Halyard into a vanity
dashboard. The right outcome is pretty and useful: visual enough to invite
daily use, precise enough to support billing, audit, and decision-making.

## Product Thesis

If The Bridge answers "is my work being captured correctly?", Usage
Analytics answers "what does my AI work pattern look like?"

The view should be local-first, calm, compact, and visually rewarding. It
should make Halyard feel better than any single-tool stats page because it can
combine Claude Code, Cursor, Gemini CLI, Codex, and future tools into one
privacy-preserving usage record.

## Goals

- Provide a beautiful overview of AI usage across supported tools.
- Show session, token, model, active-day, streak, and peak-hour metrics.
- Show time-series trends for all time, 30 days, and 7 days.
- Show model share using input/output tokens, cost, and sessions where useful.
- Show tool and surface share so users can compare Claude Code (by cli/desktop),
  Cursor, Gemini CLI, Codex, and future collectors.
- Preserve Halyard's local-first privacy contract: no prompts, transcripts,
  code contents, or secrets.
- Reuse the same parsers and report services as CLI reports and the dashboard.
- Provide graceful handling for missing data, unavailable token counts, and
  older log lines.

## Non-Goals

- Replace The Bridge's operational health and attribution workflow.
- Replace invoices, cost allocation, or audit appendices.
- Require a hosted service or cloud account.
- Capture prompts, transcripts, or source code.
- Pretend every tool exposes identical telemetry.
- Rank developers or produce productivity scores.

## Audiences

### Individual developer or freelancer

Wants to understand usage patterns, explain AI cost to clients, and see which
models or tools are actually carrying the work.

### Small AI shop or technical lead

Wants a readable usage snapshot across projects and tools before digging into
cost centers, budgets, or invoice evidence.

### Future team/admin user

Wants rollups that are comprehensible without exposing private work content.
Team analytics are later scope; the local individual experience comes first.

## Primary Experience

Usage Analytics should be available from the local dashboard and should also be
summarizable from the CLI.

Suggested entry points:

```bash
halyard dashboard
halyard usage
halyard usage --json
```

The dashboard view should include two primary tabs:

- **Overview** - summary cards, activity heatmap, active-day/streak metrics,
  peak hour, favorite model, token comparison copy, and tool share.
- **Models** - stacked daily usage chart, model legend, token/cost/session
  breakdowns, model share, and missing-cost/token data warnings.

The view should support these time ranges:

- all time;
- 30 days;
- 7 days.

The default should be 30 days for a personal analytics feeling, unless the
available data set is smaller, in which case the view should still render
clearly.

## Core Metrics

### Overview

- Sessions captured.
- Interaction/message count when available, otherwise marked unavailable.
- Total tokens, split into input, output, cache read, and cache write where
  available.
- Total direct cost and, when configured, allocated plan cost.
- **Tool and surface breakdown** — tool mix by sessions/tokens/cost, including
  advisory client-surface sub-buckets (cli/desktop/ide) for Claude Code. Since
  v3.3, rejections for Claude Code and Codex are captured as a subset of
  tool errors and labeled as such to avoid double-counting confusion.
- Active days in selected range.
- Current streak and longest streak in selected range.
- Peak hour based on session start time.
- Favorite model by primary metric, defaulting to tokens when available and
  falling back to sessions.
- Tool mix by sessions, tokens, and cost.
- Unattributed session count as a subtle but visible warning.

### Activity Heatmap

The overview should include a compact day-level activity grid.

The heatmap should:

- cover the selected range;
- use day cells with stable dimensions;
- encode activity by token volume, falling back to session count when tokens
  are unavailable;
- indicate missing token data distinctly from zero activity;
- expose exact day totals in accessible labels or hover text in the web view;
- avoid implying unavailable data is zero.

### Models

The models tab should include:

- stacked daily bars by model;
- input/output token totals per model;
- cost per model where cost is available;
- session count per model;
- share percentage by selected metric;
- clear indication of unknown, unavailable, or zero-cost model rows.

The chart should be able to switch between:

- tokens;
- cost;
- sessions.

The first implementation may choose one default metric if the control is too
large for MVP, but the data model should support all three.

## UX Direction

Usage Analytics should be more visually expressive than The Bridge, but
still work-focused and compact.

Design principles:

- Dark local dashboard style consistent with Halyard.
- No landing-page hero, marketing copy, or decorative-only sections.
- Top-level stats should be readable in under 10 seconds.
- Charts should explain the shape of use, not just decorate the page.
- Cards should be compact, with stable dimensions and no layout shift on
  refresh.
- Use semantic color: blue/cyan for usage, green for healthy/captured, amber
  for incomplete or inferred, red only for actual broken or missing states.
- Keep model colors distinct enough to compare without becoming rainbow noise.
- Do not use one hue family for the whole page.
- Use tabs for Overview/Models and segmented controls for time range.
- Include accessible labels for chart cells and bars.

## Data Sources

Usage Analytics reads from:

- `ai-sessions.log`;
- append-only amendment records applied by the existing parser;
- `ai-plans.toml` when cost allocation is requested;
- selected state under `~/.halyard/` only when needed for local context.

It should not read prompts, transcripts, code contents, or arbitrary files.

## Data Quality Rules

- Token totals must separate available zero values from unavailable token data.
- Cost totals must distinguish captured direct API cost from allocated plan
  cost and missing cost.
- Older sessions with incomplete fields should remain visible.
- Unknown models and tools should be grouped by their captured label, not
  silently discarded.
- Streaks and active days should be based on local dates.
- Future-dated rows should be included only if they are present in the selected
  data set, but the UI should make the selected date range clear.
- Duplicate records are not solved by this view; it should use the same parser
  semantics as existing reports.

## Privacy And Safety

Usage Analytics must never display:

- prompts;
- transcripts;
- source code;
- file contents;
- API keys or secrets;
- raw home-directory paths unless needed for local diagnostics.

The view should show metadata only: time, tool, model, tokens, cost, project,
branch, attribution status, and operational telemetry.

## MVP Scope

MVP should include:

- shared usage analytics service model;
- CLI summary command or JSON output;
- dashboard Usage view with Overview and Models tabs;
- all/30d/7d range control;
- summary metric cards;
- activity heatmap;
- stacked daily model chart;
- model breakdown table;
- tool breakdown table or compact legend;
- empty states and missing-data states;
- tests for aggregation, ranges, streaks, model share, and unavailable tokens.

## Later Scope

- Export PNG/SVG/CSV.
- Weekly/monthly comparison deltas.
- Per-project and per-branch filters.
- Model family grouping.
- "Receipts" for individual sessions, including resume command where present.
- Team rollups after org sync and security posture are ready.
- Optional chart embedding in invoice evidence appendices.

## Success Criteria

- A user can open the Usage view and understand their AI usage pattern within
  10 seconds.
- Halyard's view feels at least as useful as single-tool stats pages because it
  combines multiple tools.
- The Overview tab shows active days, streaks, peak hour, favorite model,
  sessions, and token totals for all/30d/7d ranges.
- The Models tab shows model share over time and by aggregate totals.
- Missing or unavailable token/cost data is visible and not misrepresented.
- No prompt, transcript, code, or secret data is exposed.
- The implementation reuses existing log parsing and report services.

