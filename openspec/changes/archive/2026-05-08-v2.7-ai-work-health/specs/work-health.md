# Spec: v2.7 — AI Work Health

## Command

### WHEN the user runs `halyard health`
THEN the command reads sessions from the project directory or hub for the
default period (month) and prints the work health report to stdout.
Exit code is always 0.

### WHEN the user runs `halyard health --period today`
THEN only sessions with a start time on the current calendar day are analysed.
The same applies to `week` (last 7 days), `month` (current calendar month),
and `all` (no time filter).

### WHEN the user runs `halyard health --project acme:auth`
THEN only sessions attributed to `acme:auth` are analysed.

### WHEN the user runs `halyard health --format json`
THEN output is valid JSON matching the documented schema.
No decorative text, no Rich markup.

### WHEN no Halyard project is found and no hub is configured
THEN the command exits with code 1 and prints "No Halyard project found."

---

## Report header

### WHEN the report is rendered in text format
THEN the first non-blank line after the title MUST read:
`These are operational signals, not productivity scores.`

---

## Signal: High tool error rate

### GIVEN sessions with `tool_calls >= 5` and `tool_errors / tool_calls > 0.25`
WHEN the report is rendered
THEN those sessions are listed under "High tool error rate"
AND each row shows: timestamp, tool, project, call count, error count,
error rate percentage, and cost

### GIVEN no sessions in the period have `tool_calls` populated
WHEN the report is rendered
THEN the signal row reads "No data — requires tool_calls"
AND no sessions are listed

### GIVEN all sessions with tool_calls have error rate ≤ 0.25
WHEN the report is rendered
THEN the signal row reads "0 sessions flagged"

---

## Signal: Wall time ≫ active time

### GIVEN sessions with both `wall_seconds` and `agent_active_seconds` populated
AND `agent_active_seconds < wall_seconds * 0.30`
WHEN the report is rendered
THEN those sessions are listed under "Wall time ≫ active time"
AND each row shows: timestamp, tool, project, wall time, active time, ratio

### GIVEN no sessions have both `wall_seconds` and `agent_active_seconds`
WHEN the report is rendered
THEN the signal row reads "No data — requires agent_active_seconds"

---

## Signal: High spend, low code delta

### GIVEN sessions with `cost_usd >= 0.50` and `code_added` populated
AND `(code_added + code_removed) / cost_usd < 5.0`
WHEN the report is rendered
THEN those sessions are listed under "High spend, low code delta"
AND each row shows: timestamp, tool, project, cost, code delta

### GIVEN no sessions have `code_added` populated
WHEN the report is rendered
THEN the signal row reads "No data — requires code_added"

---

## Signal: Repeated sessions — same project and branch

### GIVEN three or more sessions share the same `project` and `branch` tag
on the same calendar day
WHEN the report is rendered
THEN those sessions are listed under "Repeated sessions — same project/branch"
AND the group label shows: project, branch, date, count

### GIVEN sessions have no branch tags
WHEN repeated-session detection runs
THEN sessions with no branch tag are grouped by project and date only

### GIVEN a project has fewer than 3 sessions on any single day
WHEN the report is rendered
THEN no sessions are listed for this signal

---

## Signal: Unattributed high-cost sessions

### GIVEN sessions with no `project` attribution and cost at or above
the 75th percentile of all session costs in the period
WHEN the report is rendered
THEN those sessions are listed under "Unattributed high-cost sessions"
AND each row shows: timestamp, tool, cost

### GIVEN all sessions have project attribution
WHEN the report is rendered
THEN the signal row reads "0 sessions flagged"

### GIVEN no sessions exist in the period
WHEN the report is rendered
THEN all signal rows read "0 sessions flagged" or "No data"
AND the footer reads "0 sessions analysed"

---

## JSON output

### WHEN `--format json` is passed
THEN the output is a single JSON object with keys:
- `period` (string)
- `session_count` (integer)
- `signals` (array of signal objects)

Each signal object has:
- `category` (string slug, e.g. `"high_error_rate"`)
- `label` (human-readable string)
- `available` (boolean — false when required fields are absent)
- `flagged_count` (integer)
- `sessions` (array of session summary objects)

### WHEN a signal is not available
THEN `flagged_count` is 0 and `sessions` is an empty array
AND `available` is false
