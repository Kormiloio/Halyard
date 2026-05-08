# Rich Session Telemetry

## ADDED Requirements

### Requirement: Optional Rich Telemetry Fields

Halyard SHALL support optional rich telemetry fields on AI session records while
preserving compatibility with existing `ai-sessions.log` records.

#### Scenario: Existing log line remains valid

- **GIVEN** an `ai-sessions.log` line without rich telemetry fields
- **WHEN** Halyard parses the line
- **THEN** the session parses successfully
- **AND** all rich telemetry fields are unset

#### Scenario: Rich telemetry fields parse successfully

- **GIVEN** an `ai-sessions.log` line with rich telemetry `key=value` pairs
- **WHEN** Halyard parses the line
- **THEN** known rich telemetry fields are populated on the session record
- **AND** unknown extension fields are ignored

### Requirement: Metadata-Only Capture

Halyard SHALL treat rich telemetry as operational metadata and SHALL NOT capture
prompts, conversation transcripts, or source code as part of this change.

#### Scenario: Resume command is unsafe

- **GIVEN** a collector can derive a resume command that includes prompt text or
  sensitive content
- **WHEN** Halyard prepares the session record
- **THEN** Halyard omits the resume command
- **AND** the rest of the session can still be written

### Requirement: Gemini CLI Enrichment

The Gemini CLI collector SHOULD populate rich telemetry fields when Gemini
history data exposes them.

#### Scenario: Gemini history contains operational telemetry

- **GIVEN** a Gemini CLI session history file contains tool calls, tool errors,
  timing, code delta, or model breakdown data
- **WHEN** Halyard finalizes the session
- **THEN** Halyard writes available rich telemetry fields to `ai-sessions.log`
- **AND** missing fields are omitted rather than inferred

#### Scenario: Gemini history contains code stats

- **GIVEN** a Gemini CLI session history file contains a `codeStats` object
  with `added` and/or `removed` fields
- **WHEN** Halyard parses the history file
- **THEN** `code_added` and `code_removed` are populated on the session record
- **AND** if `codeStats` is absent the fields are left unset

#### Scenario: Gemini history contains per-model breakdown

- **GIVEN** a session used multiple Gemini models (e.g. flash and pro)
- **WHEN** Halyard finalizes the session
- **THEN** `model_breakdown` is written as a compact `model:requests|model:requests`
  string
- **AND** `model` is set to the dominant model by output token count

#### Scenario: Resume command capture

- **GIVEN** a Gemini CLI session has a valid session_id
- **WHEN** Halyard finalizes the session
- **THEN** `resume_command` is written as `gemini --resume <session_id>`
- **AND** the value contains no prompt text or source code

### Requirement: Work-Health Display

Halyard SHOULD display rich telemetry as operational work-health signals in
local UI surfaces.

#### Scenario: Session has tool errors

- **GIVEN** a session has `tool_errors` greater than zero
- **WHEN** Glass Cockpit or the TUI displays the session
- **THEN** the UI surfaces the tool error count as `<calls>c <errors>e`
- **AND** the UI avoids presenting the signal as a productivity score

#### Scenario: Session has code delta

- **GIVEN** a session has `code_added` or `code_removed` populated
- **WHEN** Glass Cockpit displays the session in the Health column
- **THEN** the delta is shown as `+<added>/-<removed>`

#### Scenario: Project drill-down shows aggregated health

- **GIVEN** a project has sessions with tool telemetry
- **WHEN** the TUI project pane renders the Work Health section
- **THEN** the section shows total tool calls, total errors, error rate percentage,
  average wall time, and aggregated code delta
- **AND** the most recent resume command is shown if available

#### Scenario: Rich telemetry is unavailable

- **GIVEN** a session was captured from a tool that does not expose rich
  telemetry
- **WHEN** Glass Cockpit or the TUI displays the session
- **THEN** missing rich telemetry is shown as unavailable (`—`) or omitted
- **AND** the session remains visible with its baseline metadata

### Requirement: Tool Call Aggregation in Reports

Halyard SHOULD surface aggregate tool call counts in `halyard log` output.

#### Scenario: Sessions with tool telemetry in period

- **GIVEN** the active period contains sessions with `tool_calls` populated
- **WHEN** the user runs `halyard log "what happened this month?"`
- **THEN** the answer includes the total tool call count and error count
  in addition to cost and session count

