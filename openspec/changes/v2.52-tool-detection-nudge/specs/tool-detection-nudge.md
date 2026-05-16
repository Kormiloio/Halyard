# Spec: Unwired-Tool Detection Nudge

## Requirement: Flag installed-but-unwired live-hook tools

`halyard doctor` MUST emit a `warn` check for any tool in {Claude
Code, Cursor, Gemini CLI} whose binary is on PATH while it has
**neither** Halyard hooks **nor** the Halyard MCP server registered for
its scope. The check MUST carry an actionable `fix` string.

### Scenario: installed, zero integration
- GIVEN `cursor` is on PATH, no Cursor hooks, no `mcpServers.halyard`
  in `~/.cursor/mcp.json`
- WHEN `halyard doctor` runs
- THEN the report contains a check `unwired.cursor`, status `warning`,
  with a fix referencing `halyard setup` / `halyard install-hook-cursor`.

### Scenario: hooks present → no nudge
- GIVEN `cursor` is on PATH and Cursor hooks are installed
- WHEN `halyard doctor` runs
- THEN there is no `unwired.cursor` check.

### Scenario: MCP-only present → no nudge
- GIVEN `gemini` is on PATH, no Gemini hooks, but
  `~/.gemini/settings.json` has `mcpServers.halyard`
- WHEN `halyard doctor` runs
- THEN there is no `unwired.gemini` check.

### Scenario: tool absent → no nudge
- GIVEN `claude` is not on PATH
- WHEN `halyard doctor` runs
- THEN there is no `unwired.claude` check.

## Requirement: Flag Codex history not yet imported

`halyard doctor` MUST emit a `warn` check when Codex Desktop session
history exists on disk but no Codex sessions are present in the ledger,
with fix `halyard import-codex`.

### Scenario: history present, nothing imported
- GIVEN Codex history directory exists and the ledger has zero
  `codex-app` sessions
- WHEN `halyard doctor` runs
- THEN the report contains `unwired.codex`, status `warning`, fix
  `halyard import-codex`.

### Scenario: already imported → no nudge
- GIVEN at least one `codex-app` session is in the ledger
- WHEN `halyard doctor` runs
- THEN there is no `unwired.codex` check.

## Requirement: Exit-code contract preserved

Unwired-tool checks MUST be `warning`, never `error`. `has_errors(report)`
MUST stay False when the only non-ok checks are `unwired.*`, so
`halyard doctor`'s exit code (used by scripts/CI) is unchanged.

## Requirement: No daemon, on-demand only

Detection MUST run only inside `build_doctor_report()` (i.e. when the
user invokes `doctor` or a surface that calls it). No background
process, watcher, or scheduled task may be introduced.
