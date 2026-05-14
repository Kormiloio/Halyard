# Spec: Tool Visibility

## CLI — By Tool Section

**Scenario 1: "By tool" section appears in report output**

GIVEN a project with sessions from `claude-code` and `codex`
WHEN the user runs `halyard report`
THEN the output contains a "By tool" section
AND the section lists both `claude-code` and `codex`

---

**Scenario 2: Zero-cost tool appears in "By tool" section**

GIVEN a project with 15 Codex sessions all having `cost_usd = 0.00`
AND 1 Claude Code session with `cost_usd = 5.00`
WHEN the user runs `halyard report`
THEN the "By tool" section lists `codex` with session count 15
AND `codex` appears in the output regardless of its zero cost

---

**Scenario 3: Tool rows are sorted by session count, not cost**

GIVEN tool A has 15 sessions and `cost_usd = 0.00`
AND tool B has 1 session and `cost_usd = 5.00`
WHEN the user runs `halyard report`
THEN tool A appears before tool B in the "By tool" section

---

**Scenario 4: Token counts are shown per tool**

GIVEN a project with codex sessions having a total of 1,400,000 input tokens
and 9,000 output tokens
WHEN the user runs `halyard report`
THEN the `codex` row in "By tool" shows a token total matching the sum of
input and output tokens for those sessions

---

**Scenario 5: "By tool" does not break "By model" or "By project"**

GIVEN any project
WHEN the user runs `halyard report`
THEN "By project" and "By model" sections appear with unchanged content
AND their sort order and cost figures are unaffected

---

## Dashboard — Tool Table Bar Metric

**Scenario 6: Zero-cost tool renders a non-zero bar in the tool table**

GIVEN a dashboard with `by_tool_usage` containing:
  - `claude-code`: 96 sessions, cost $1,687.85, session_share 0.87
  - `codex`: 15 sessions, cost $0.00, session_share 0.13
WHEN the tool table HTML is rendered
THEN the `codex` row contains `width:13%` (or equivalent non-zero session share)
AND the `claude-code` row contains `width:87%`

---

**Scenario 7: Tool table sorts by session count, not cost**

GIVEN tool A has session_share 0.9 and cost $0.00
AND tool B has session_share 0.1 and cost $100.00
WHEN the tool table HTML is rendered
THEN tool A's row appears before tool B's row in the table

---

**Scenario 8: Tool table shows tokens column**

GIVEN a dashboard with one codex tool bucket having 1,409,275 total tokens
WHEN the tool table HTML is rendered
THEN the rendered HTML contains a token count for the codex row

---

**Scenario 9: Project and model tables are unchanged**

GIVEN any dashboard state
WHEN the dashboard is rendered
THEN `_bucket_table(report.by_project, "Project")` output is identical to its
pre-v2.30 output
AND `_bucket_table(report.by_model, "Model")` output is identical

---

## Dashboard — Usage Analytics Panel

**Scenario 10: Usage panel shows more than four tools**

GIVEN a project with sessions from five distinct tools
WHEN the usage analytics panel is rendered
THEN all five tools appear in the panel (not just the top 4)

---

**Scenario 11: Usage panel shows token counts**

GIVEN a tool bucket with `tokens = 1_409_275`
WHEN the usage analytics tool rows are rendered
THEN the HTML for that tool contains a formatted token count (e.g. "1.4M")

---

## Edge Cases

**Scenario 12: Single tool — no division-by-zero**

GIVEN a project with sessions from exactly one tool
WHEN the tool table is rendered
THEN the single tool renders with `width:100%`
AND no exception is raised

---

**Scenario 13: No sessions — graceful empty state**

GIVEN a project with zero AI sessions
WHEN `halyard report` is run
THEN the "By tool" section is omitted or shows an empty-state message
AND no exception is raised

---

**Scenario 14: All sessions have unknown tool**

GIVEN sessions where `tool` is `None` or empty
WHEN the tool aggregation runs
THEN they are grouped under a label (e.g. `unknown`)
AND no exception is raised
