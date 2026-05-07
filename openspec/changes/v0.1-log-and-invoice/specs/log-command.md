# Spec: `halyard log` — AI Agent Query Command

## Overview

`halyard log <query>` invokes a single-turn Claude SDK tool-use call that reads
the current project's (or hub's) `ai-sessions.log` and answers a natural
language question about the captured data.

---

## Scenarios

### WHEN the user runs `halyard log "what did I spend on AI this month"`
THEN the command calls the Claude SDK with the query and a set of tool
definitions, the model issues one or more tool calls to read and summarize
session data, and the final response is rendered to the terminal as a
human-readable Rich panel.

### WHEN the user runs `halyard log --json "summarize by project"`
THEN the command emits a JSON object to stdout instead of rendering Rich output.
The JSON structure is a `LogQueryResponse` with a `projects` array, each entry
containing `project`, `cost_usd`, `input_tokens`, `output_tokens`,
`session_count`, and `date_range`.

### WHEN the command is run outside a Halyard project directory AND no hub is configured
THEN the command prints: `No project or hub found. Run 'halyard init' to create
a project, or 'halyard set-hub' to configure a hub.` and exits with code 1.

### WHEN the command is run outside a Halyard project directory BUT a hub is configured
THEN the command uses the hub's `ai-sessions.log` as the data source and
prepends `[hub]` to the response header so the user knows which log was queried.

### WHEN `ai-sessions.log` exists but is empty
THEN the model returns a response noting that no sessions have been captured
yet and suggesting `halyard sample-session` or hook installation.

### WHEN the Anthropic API key is not configured (`ANTHROPIC_API_KEY` not set)
THEN the command prints: `ANTHROPIC_API_KEY not set. Halyard log requires an
Anthropic API key.` and exits with code 1.

### WHEN the SDK call times out or returns an API error
THEN the command prints the error message with context and exits with code 1.
No partial output is written.

### WHEN the user passes `--model <model-id>`
THEN that model is used for the SDK call instead of the default.
The default model is `claude-haiku-4-5` (cost-efficient for retrieval queries).

---

## Tool definitions available to the agent

### `read_sessions`
Parameters: `project` (optional string), `start` (optional ISO date), `end`
(optional ISO date), `tool` (optional string), `limit` (optional int, default 200)

Returns a filtered list of sessions from `ai-sessions.log`. Each session
includes: start, end, tool, model, input_tokens, output_tokens, cost_usd,
project, tags.

### `summarize_by_project`
Parameters: `start` (optional ISO date), `end` (optional ISO date)

Returns aggregated cost, input_tokens, output_tokens, and session_count grouped
by project slug.

### `summarize_by_model`
Parameters: `start` (optional ISO date), `end` (optional ISO date)

Returns aggregated cost, input_tokens, output_tokens, and session_count grouped
by model identifier.

### `cost_by_branch`
Parameters: `branch` (string), `start` (optional ISO date), `end` (optional
ISO date)

Returns all sessions tagged `branch:<branch>` and their total cost.

### `read_timeclock`
Parameters: `start` (optional ISO date), `end` (optional ISO date)

Returns human time entries from `time.timeclock` in the project directory.
Each entry includes: project, start, end, duration_hours.

---

## Response structure (`LogQueryResponse`)

```python
@dataclass
class LogQueryResponse:
    answer: str                       # human-readable answer to the query
    data_source: str                  # "project" or "hub" + path
    period: str                       # e.g., "May 2026" or "all time"
    cost_usd_total: float | None      # total cost if the query is about cost
    session_count: int | None         # session count if relevant
    projects: list[ProjectSummary]    # populated for summarize queries
    models: list[ModelSummary]        # populated for model breakdown queries
    sessions: list[SessionRow]        # populated for session list queries
```

The model is instructed to populate only the fields relevant to the query.
Irrelevant fields are `None` or empty lists.

---

## CLI flags

| Flag | Description |
|------|-------------|
| `--json` | Emit `LogQueryResponse` as JSON instead of Rich output |
| `--model <id>` | Override the default model (`claude-haiku-4-5`) |
| `--log <path>` | Use a specific `ai-sessions.log` file instead of auto-detection |
| `--period <period>` | Pre-set the time period: `today`, `week`, `month`, `all` (default: `month`) |
