# Spec: AI Agent Loop

## Scenario: User asks a complex question requiring tool use
**Given** the user has logged sessions for `claude-code` and `cursor`
**And** the user runs `halyard log "How much did we spend on Claude vs Cursor this month?" --agent claude`
**When** the agent evaluates the query
**Then** the agent calls the `summarize_by_model` and/or `read_sessions` tools
**And** the agent formulates a natural language answer comparing the two
**And** the CLI prints the natural language answer along with the structured model breakdown table.

## Scenario: Missing API Key
**Given** the user has no `ANTHROPIC_API_KEY` set
**When** the user runs `halyard log "..." --agent claude`
**Then** Halyard exits with a clear error instructing the user to set the `ANTHROPIC_API_KEY` environment variable.

## Scenario: Tool Failure
**Given** a tool call fails or returns an error
**When** the agent receives the error result
**Then** the agent should attempt to explain the failure or retry if appropriate, rather than crashing the CLI.
