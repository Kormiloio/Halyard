# Design: v0.2 — AI Agent Loop

## Architecture

We use the **Anthropic SDK tool-use** capability. The agent loop is a single-turn or multi-turn execution (max 3 turns).

### 1. Tools provided to Claude
We will expose the following tools to Claude:
- `read_sessions(start_date?, end_date?, tool?, project?, limit?)`: Returns a list of individual AI sessions matching filters.
- `summarize_by_project(start_date?, end_date?)`: Returns aggregated costs and token counts grouped by project.
- `summarize_by_model(start_date?, end_date?)`: Returns aggregated costs and token counts grouped by model.
- `read_timeclock(start_date?, end_date?)`: Returns human time entries from `time.timeclock`.

### 2. Execution Flow
1. User runs `halyard log "How much did we spend on Claude this week?" --agent claude`.
2. `log_agent.py` initializes the Anthropic client.
3. System prompt establishes Claude's role as the Halyard AI assistant.
4. Claude evaluates the query and calls `summarize_by_model(start_date="...", end_date="...")`.
5. Halyard executes the tool locally and returns the JSON result to Claude.
6. Claude generates the final natural language answer.
7. Halyard parses the response and returns a `LogQueryResponse` (incorporating Claude's text answer and the structured summary data for rendering).

### 3. Constraints
- **Provider Neutrality**: The tools (data layer) are neutral Python functions. Claude is simply one possible reasoning engine.
- **Structured Rendering**: The CLI will still render the standard tables (projects, models) if Claude's tool calls populate them, keeping the output familiar.
