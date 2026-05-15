# Proposal: v2.30 — Tool Visibility

## Why this change

Halyard supports five AI tools today: Claude Code, Codex, Gemini CLI, VS Code
manual capture, and Cursor. Two of those — Codex and Gemini — run on credit
plans where `cost_usd = 0.00` for every session. A third, VS Code manual
capture, also logs at zero cost.

Every summary surface in Halyard — the CLI report and the web dashboard — is
cost-dominant. Bars, sort order, and relative sizing are all derived from
`cost_usd`. Tools on credit plans are present in the data but invisible to the
eye: their bars are 0% wide, they sort below paid tools regardless of usage
volume, and the CLI omits the "By tool" section entirely.

A user who runs Codex or Gemini heavily alongside Claude Code receives no
signal of that in any Halyard output. They see $0.00 next to the tool name and
nothing else. Session counts and tokens are buried.

This is not a theoretical complaint. On 2026-05-14, a user running an active
Codex session asked why Codex was not appearing in the web UI. Investigation
showed 15 Codex sessions correctly stored in the log, but not surfaced by the
dashboard in any meaningful way.

---

## What this change does

Replace cost as the primary metric for the tool breakdown on all surfaces.
Session count becomes the sort key and bar metric for the "By tool" view
everywhere. Tokens appear alongside session count. Cost is retained as a
secondary column.

Three concrete changes:

### 1. CLI — add "By tool" to `halyard report`

`halyard report` renders "By project" and "By model" but has no "By tool"
section. Add one. Each row shows: tool name, session count, total tokens
(input + output), and cost. Sort descending by session count. Show all tools
with ≥ 1 session; do not filter on cost.

### 2. Dashboard — fix the "By Tool" table bar metric

`_bucket_table(report.by_tool, "Tool")` renders bars using cost percentage.
All credits-billed tools render at 0% width. Replace the cost-based bar with a
session-count-based bar in the tool table. A tool with 15 sessions and 0 cost
should fill the same proportion of the bar as it would if it had 15 sessions
and non-zero cost.

The model and project tables are unaffected — cost is the right metric there.

### 3. Dashboard — add tokens to the tool usage panel; remove the cap

`_usage_tool_rows` in the usage analytics panel caps the tool list at four
entries and shows only session count and session share. Remove the cap (show
all tools). Add total tokens to each row.

---

## What this change does not do

- Does not change the data model for `by_project` or `by_model` — cost is the
  correct metric for both.
- Does not add new data collection. All token and session data is already
  present in `AiReport.sessions`.
- Does not change how costs are reported for paid tools — Claude Code sessions
  still show full cost figures.
- Does not touch the log format, the timeclock, or any stored data.

---

## Files changed

| File | Change |
|---|---|
| `src/halyard/cli.py` | Add "By tool" section to `halyard report` output |
| `src/halyard/dashboard.py` | Fix `_bucket_table` bar for tools to use session%; remove `[:4]` cap in `_usage_tool_rows`; show tokens in tool rows |
| `src/halyard/reports.py` | Enrich `_bucket_costs` or add `_tool_buckets_for_report()` so `AiReport.by_tool` carries tokens |
| `tests/test_reports.py` | Confirm `by_tool` buckets include correct token totals |
| `tests/test_dashboard.py` | Confirm tool table bars use session% not cost%; confirm all tools render; confirm tokens shown |

---

## Success criteria

1. `halyard report` output includes a "By tool" section; Codex/Gemini sessions
   appear with correct session counts and token totals.
2. A tool with `cost_usd = 0.00` and 15 sessions renders a non-zero bar in the
   dashboard tool table.
3. The dashboard usage panel shows all tools (not just the top 4) with token
   counts visible.
4. `by_project` and `by_model` rendering is unchanged.
5. All existing tests pass; ≥ 8 new tests added.
