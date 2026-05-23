# v2.51 — MCP Auto-Registration

## Problem

v2.50 shipped the read-only `halyard mcp` server, but registering it
with an MCP client is still a manual one-time step: the end user has to
hand-edit a JSON config file. The repo-root `.mcp.json` only helps
people working *inside the Halyard repo* with Claude Code — a real end
user who `pip install halyard` to track their own AI work gets nothing
automatic.

Halyard already auto-wires itself into the same clients for hook
collectors (`halyard init` detects `claude`/`cursor`/`gemini` on PATH
and merges hook entries into their configs). MCP registration needs the
exact same mechanism — it just writes to a different key in a
(sometimes different) config file.

## Goal

During Halyard setup, auto-register the `halyard mcp` server with every
detected MCP client, so the end user never edits a config file.

- `halyard init` (and `halyard setup`) registers the MCP server for
  each detected client alongside hook installation, gated on the same
  PATH detection.
- Explicit commands `halyard install-mcp-claude|cursor|gemini` for
  manual / re-run use, mirroring `install-hook-*`.
- Idempotent: re-running replaces the stale `halyard` server entry
  (e.g. moved venv) and preserves foreign servers (e.g. `claude-mem`).

## Target config files (confirmed on a real machine)

All three clients use the identical `mcpServers` object shape; only the
file differs:

- **Claude Code** — `~/.claude.json` (user scope; works in every
  project, equivalent to `claude mcp add -s user`).
- **Cursor** — `~/.cursor/mcp.json`.
- **Gemini CLI** — `~/.gemini/settings.json`.

Entry written (binary resolved via the existing trusted `_halyard_exe`):

```json
{ "mcpServers": { "halyard": { "command": "<halyard exe>", "args": ["mcp"] } } }
```

## Constraints honored

- **No clobber.** Reuses `_load_existing_settings` (refuses to
  overwrite invalid-JSON / non-object configs) and `_write_settings`
  (clean error on read-only files). `~/.claude.json` is large and
  critical — only the `mcpServers.halyard` key is touched; every other
  key is preserved.
- **Idempotent / no churn.** `_settings_unchanged` makes a no-op run
  byte-stable. Delete-and-rebuild only the `halyard` server, foreign
  servers untouched (same philosophy as the Cursor/Gemini hook
  installers).
- **Best-effort in auto path.** Like hooks, a read-only client config
  must not hard-fail `halyard init` — the auto path swallows `OSError`
  and reports; the explicit command surfaces a clean actionable error.
- **Detection-gated.** Only registers for a client whose binary is on
  PATH, identical to hook auto-install.

## Non-goals

- No new MCP tools or server behavior (v2.50 surface unchanged).
- No project-scoped Claude MCP variant — user scope only (the repo
  `.mcp.json` already covers the Halyard repo itself).
- No uninstall command (out of scope; manual key removal is trivial).

## Out of scope

Bundling Halyard as a full Claude Code plugin (skills/UI) — later.
