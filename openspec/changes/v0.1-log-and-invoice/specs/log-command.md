# Spec: `halyard log` — AI Agent Query Command

## Overview

`halyard log <query>` queries Halyard's local metadata files through a
provider-neutral log query layer. The default `local` agent is deterministic
and works offline. Future model-backed agents, starting with `claude`, may use
the same local tools and response schema to answer richer natural-language
questions.

The data source is always Halyard's local files (`ai-sessions.log`,
`time.timeclock`, plans, budgets, ledger), not the agent provider. Claude,
OpenAI, Gemini, or any future agent is only the reasoning layer.

---

## Scenarios

### WHEN the user runs `halyard log "what did I spend on AI this month"`
THEN the command uses the default `local` agent, reads the current project's
local logs, and renders a human-readable summary.

### WHEN the user runs `halyard log --json "summarize by project"`
THEN the command emits a JSON object to stdout instead of rendering Rich output.
The JSON structure is a `LogQueryResponse` with a `projects` array, each entry
containing `project`, `cost_usd`, `input_tokens`, `output_tokens`,
`session_count`, and `date_range`.

### WHEN the user runs `halyard log --agent local <query>`
THEN the command uses only deterministic local code, works offline, and does
not require an API key.

### WHEN the local query mentions a known tool
THEN the local provider filters sessions to that tool. Known tool mentions
include `cursor`, `claude`, `claude code`, `gemini`, `gemini cli`, and `codex`.
For example, `halyard log "what did Cursor cost this week?"` summarizes only
Cursor sessions.

### WHEN the local query mentions a simple period
THEN the local provider applies that period unless an explicit `--period` flag
was passed. Recognized phrases include `today`, `this week`, `week`, `this
month`, `month`, `all time`, and `all`.

### WHEN the local query mentions a project, model, or branch
THEN the local provider filters sessions by the matching project slug, model
substring, or `branch:<name>` tag. Explicit flags (`--project`, `--model`,
`--branch`, `--tool`) override inferred query intent.

### WHEN the user runs `halyard log --agent claude <query>`
THEN the command routes through the Claude provider if implemented and
configured. If the provider is not yet implemented, the command prints a clear
message that `--agent claude` is unavailable and recommends `--agent local`.

### WHEN the command is run outside a Halyard project directory AND no hub is configured
THEN the command prints: `No project or hub found. Run 'halyard init' to create
a project, or 'halyard set-hub' to configure a hub.` and exits with code 1.

### WHEN the command is run outside a Halyard project directory BUT a hub is configured
THEN the command uses the hub's `ai-sessions.log` as the data source and
prepends `[hub]` to the response header so the user knows which log was queried.

### WHEN `ai-sessions.log` exists but is empty
THEN the model returns a response noting that no sessions have been captured
yet and suggesting `halyard sample-session` or hook installation.

### WHEN the Claude provider is selected and the Anthropic API key is not configured (`ANTHROPIC_API_KEY` not set)
THEN the command prints: `ANTHROPIC_API_KEY not set. Halyard log requires an
Anthropic API key for --agent claude.` and exits with code 1. The local agent
continues to work without a key.

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
| `--agent <local|claude>` | Select the query provider. Default: `local` |
| `--model <id>` | Override the provider model when using a model-backed agent |
| `--tool <tool>` | Filter deterministic local queries to a tool |
| `--project <slug>` | Filter deterministic local queries to a project |
| `--model-filter <text>` | Filter deterministic local queries to model names containing text |
| `--branch <name>` | Filter deterministic local queries to sessions tagged `branch:<name>` |
| `--log <path>` | Use a specific `ai-sessions.log` file instead of auto-detection |
| `--period <period>` | Pre-set the time period: `today`, `week`, `month`, `all` (default: `month`) |
