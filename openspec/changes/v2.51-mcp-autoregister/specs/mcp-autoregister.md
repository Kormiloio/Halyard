# Spec: MCP Auto-Registration

## Requirement: Auto-register on init

`halyard init` (unless `--no-interactive`) MUST register the `halyard
mcp` server with every MCP client whose binary is on PATH, using the
same detection as hook auto-install.

### Scenario: Claude Code detected
- GIVEN `claude` is on PATH and `~/.claude.json` exists
- WHEN `halyard init` runs
- THEN `~/.claude.json` gains `mcpServers.halyard = {command:<exe>,
  args:["mcp"]}` and every other key is preserved.

### Scenario: client absent
- GIVEN `gemini` is not on PATH
- WHEN `halyard init` runs
- THEN no Gemini config is created and init still succeeds.

### Scenario: read-only config in auto path
- GIVEN a client config is not writable
- WHEN `halyard init` runs
- THEN init does not crash; the failure is reported and other clients
  still get registered.

## Requirement: Explicit commands

`halyard install-mcp-claude|cursor|gemini` MUST register the server for
that one client and exit 0 on success, exit 1 with an actionable
message if the config is invalid/unwritable.

## Requirement: Idempotent, foreign-preserving

Re-running MUST result in exactly one `halyard` server entry, MUST
overwrite a stale executable path, and MUST NOT read or modify any
non-`halyard` server entry.

### Scenario: foreign server preserved
- GIVEN `~/.cursor/mcp.json` has `mcpServers.claude-mem`
- WHEN `halyard install-mcp-cursor` runs
- THEN `claude-mem` is unchanged and `halyard` is added.

### Scenario: no-op is byte-stable
- GIVEN the `halyard` entry is already current
- WHEN the installer runs again
- THEN the file content is byte-identical (no rewrite).

## Requirement: No clobber

A client config that is non-empty but not a JSON object, or whose
`mcpServers` is not an object, MUST NOT be overwritten; the installer
raises `HookWriteError` (explicit path) or is skipped (auto path).
