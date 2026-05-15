# Tasks: v0.2 — AI Agent Loop

## Spec & design
- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/agent-loop.md
- [x] Write design.md (SDK structured output approach, tool dispatch)

## `src/halyard/log_agent.py` — SDK Integration
- [x] Add `anthropic` import and initialization.
- [x] Define tool schemas (JSON schema for Anthropic API) for `read_sessions`, `summarize_by_project`, `summarize_by_model`, and `read_timeclock`.
- [x] Implement `_execute_tool(name, arguments)` to route tool calls to existing Halyard report functions.
- [x] Implement the `claude` provider in `run_log_query`:
  - Fetch `ANTHROPIC_API_KEY` from env (raise clear `LogAgentError` if missing).
  - Construct system prompt with current date/time and project context.
  - Send user query + tools to Anthropic API.
  - Handle `tool_use` stop reason: execute tools, append results, and call API again.
  - Extract final text response.
  - Populate `LogQueryResponse` with the text answer and any relevant bucket data gathered during tool execution.

## `src/halyard/cli.py`
- [x] Remove the `NotImplementedError` for `--agent claude`.
- [x] Ensure API errors (e.g., rate limits, auth errors) are caught and presented cleanly via `LogAgentError`.

## Tests
- [x] `test_run_log_query_claude_no_api_key` — raises error if no key.
- [x] `test_run_log_query_claude_success` — mocks Anthropic SDK to simulate tool call and final response, asserts `LogQueryResponse` is correctly formed.

## Quality
- [x] Run full test suite — all passing
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
