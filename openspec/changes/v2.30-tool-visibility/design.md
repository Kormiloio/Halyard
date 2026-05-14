# Design: v2.30 — Tool Visibility

## Current data model

Two separate aggregation types exist today:

**`CostBucket`** (`reports.py`) — `label`, `cost_usd`, `sessions`
Used for `AiReport.by_project`, `AiReport.by_model`, `AiReport.by_tool`.
Built by `_bucket_costs()`, which takes `(label, cost_usd)` pairs and groups
by label. No token data.

**`ToolUsageBucket`** (`usage.py`) — `tool`, `sessions`, `tokens`, `cost_usd`,
`session_share`
Used only in `UsageAnalytics.by_tool`. Built by `_tool_buckets()`. Has tokens
and session share. Sorted by `session_share` descending.

The web dashboard uses both:
- `_bucket_table(report.by_tool, "Tool")` — line 636, main report section, uses
  `CostBucket`, bars are `cost%`
- `_usage_tool_rows(usage.by_tool[:4])` — line 1068, usage analytics panel,
  uses `ToolUsageBucket`, capped at 4, no tokens shown

The CLI uses only `CostBucket` and does not render `by_tool` at all.

---

## Design decision: enrich `AiReport.by_tool`, do not change its type

Changing `AiReport.by_tool` from `list[CostBucket]` to `list[ToolUsageBucket]`
would be the cleanest long-term shape. However, it is a type-breaking change
that touches `build_ai_report()`, `build_dashboard_state()`, every call site
of `report.by_tool`, and the dashboard render path.

Instead:

1. Add a new field `AiReport.by_tool_usage: list[ToolUsageBucket]` built from
   the same session list.
2. Keep `AiReport.by_tool: list[CostBucket]` for backward compatibility.
3. The CLI and the dashboard tool table use `by_tool_usage` (session-sorted,
   with tokens).
4. The usage panel `_usage_tool_rows` already uses `UsageAnalytics.by_tool` —
   remove its cap and add token display there.

`_tool_buckets()` in `usage.py` is private. Move it (or an equivalent) to
`reports.py` so `build_ai_report()` can call it without a cross-module
dependency on `usage.py`.

---

## Sort order

Tool breakdown sorted by `sessions` descending everywhere. Ties broken by
`tokens` descending, then alphabetically by tool name. This ensures a tool
with 15 sessions and $0.00 cost ranks above a tool with 1 session and $10.00
cost.

---

## CLI rendering

New "By tool" section in `halyard report`, positioned after "By model":

```
By tool
  claude-code          96 sessions   8.3M tokens   $1,687.85
  codex                15 sessions   1.4M tokens      $0.00
  gemini                1 session    180K tokens      $0.00
```

Columns: tool name (left-padded to align), session count, total tokens
(input + output + cache, formatted with compact notation), cost. Same Rich
formatting used by "By model". Sessions column uses plural "session/sessions"
correctly.

Tokens column is omitted if no session in the period has token data
(`tokens_available` is False for all sessions of that tool). This prevents
confusing "0 tokens" rows for tools that only log totals.

---

## Dashboard — main report tool table

`_bucket_table` is generic and used for both project and tool breakdowns.
Rather than forking it, add a dedicated `_tool_table(buckets: list[ToolUsageBucket])` 
function that:

- Sorts by `sessions` descending (already done by `_tool_buckets`)
- Bar width = `session_share * 100` (not cost%)
- Columns: Tool · Sessions · Tokens · Cost
- No row cap — show all tools

Replace the call at line 636:
```python
# before
{_bucket_table(report.by_tool, "Tool")}
# after
{_tool_table(report.by_tool_usage)}
```

---

## Dashboard — usage analytics panel (`_usage_tool_rows`)

Current: capped at `[:4]`, shows sessions + session%, no tokens.

Changes:
- Remove `[:4]` cap — show all tools
- Add token count to each row: `{sessions} sessions · {compact_number(tokens)} tokens`

---

## Token computation

`ToolUsageBucket.tokens` = sum of `session.input_tokens + session.output_tokens`
for all sessions with that tool. Cache tokens (`cache_read`) are tracked in
`AiSession` but excluded from this total to avoid inflating the apparent token
count — cache reads are not new inference work.

This matches the existing `_tool_buckets` in `usage.py`.

---

## No data model migration

This change adds a new read-only field to `AiReport`. No log format changes,
no SQLite schema changes, no migration required.

---

## Test approach

- Unit tests for `_tool_buckets_for_report()`: given sessions for two tools
  where one has `cost_usd=0.0`, confirm output is sorted by sessions, tokens
  are correct, and zero-cost tool is present.
- Dashboard render tests: given `by_tool_usage` with a zero-cost tool, confirm
  the HTML output contains a non-zero `width:` style for that tool's bar.
- CLI render tests: confirm "By tool" section appears and contains the expected
  tool names and session counts.
- Regression: confirm `by_project` and `by_model` rendering is unchanged.
