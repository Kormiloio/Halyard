# v2.51 — MCP Auto-Registration: Design

## Where the code goes

`src/halyard/cli_hooks.py` — same module as the hook installers, so the
shared helpers (`_halyard_exe`, `_load_existing_settings`,
`_write_settings`, `_settings_unchanged`, `HookWriteError`,
`_run_installer`) are reused with zero new infrastructure.

## Data

```python
_MCP_SERVER_NAME = "halyard"

# Identical entry shape for all three clients; only the file differs.
def _mcp_entry(exe: str) -> dict[str, Any]:
    return {"command": exe, "args": ["mcp"]}

# client -> mcpServers config file
_MCP_CONFIG_PATHS = {
    "claude": Path.home() / ".claude.json",
    "cursor": Path.home() / ".cursor" / "mcp.json",
    "gemini": Path.home() / ".gemini" / "settings.json",
}
```

`~/.claude/settings.json` (hooks) and `~/.claude.json` (MCP, user
scope) are deliberately *different* files — Claude Code reads
user-scoped MCP servers from `~/.claude.json`.

## Core installer (one generic function, three clients)

```python
def _do_install_mcp(client: str) -> None:
    path = _MCP_CONFIG_PATHS[client]
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_existing_settings(path)        # {} if absent; raises on bad JSON
    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise HookWriteError(path, OSError("mcpServers is not an object"), ...)
    servers[_MCP_SERVER_NAME] = _mcp_entry(_halyard_exe())   # replace ours, keep foreign
    new_text = json.dumps(existing, indent=2) + "\n"
    if _settings_unchanged(path, new_text):
        console.print(f"[yellow]{label} MCP server already registered[/] ...")
        return
    _write_settings(path, new_text)
    console.print(f"[bold green]{label} MCP server registered[/] in {path}")
```

Idempotency = unconditional assignment of the single `halyard` key.
Re-running with a moved venv overwrites the stale path; foreign servers
(`claude-mem`, etc.) are never read or modified. `_settings_unchanged`
keeps a true no-op byte-stable.

## Wiring into setup

- New `_auto_install_detected_mcp()` parallels
  `_auto_install_detected_hooks()`: iterate `("claude","cursor",
  "gemini")`, `shutil.which(binary)` gate, `try/except OSError` →
  best-effort, summary print. Called from `init` right after
  `_auto_install_detected_hooks()` (skipped under `--no-interactive`).
- `halyard setup` loop: after each selected tool's hook install, also
  `_do_install_mcp(selected)` under the same `try/except OSError`.
- Explicit commands: `install-mcp-claude`, `install-mcp-cursor`,
  `install-mcp-gemini` via `_run_installer(...)`, plus an
  `install-mcp` (hidden alias) that runs all detected — mirrors the
  `install-hook-*` set.

## Safety

- `_load_existing_settings` already refuses to overwrite a non-dict or
  invalid-JSON file (raises `HookWriteError`) — protects the large
  `~/.claude.json`.
- Only `mcpServers.halyard` is assigned; `json.dumps` round-trips every
  other key unchanged (re-indented to 2 spaces, same convention as the
  hook installers — cosmetic, clients parse fine).
- Auto path swallows `OSError` so a read-only MDM-managed config never
  breaks `halyard init`; explicit command prints the actionable
  `HookWriteError` message and exits 1.

## Tests (`tests/test_v251_mcp_autoregister.py`)

Mirror `test_hook_auto_install_v218.py`:

1. Absent file → `_do_install_mcp("cursor")` creates it with
   `mcpServers.halyard.command/args == [..., "mcp"]`.
2. Existing foreign server (`claude-mem`) preserved; `halyard` added.
3. Idempotent: run twice → exactly one `halyard`, file byte-stable on
   2nd run (assert `_settings_unchanged`).
4. Stale exe path replaced on re-run (monkeypatch `_halyard_exe`).
5. Invalid-JSON config → `HookWriteError`, file untouched.
6. `_auto_install_detected_mcp()` only targets clients whose binary is
   `shutil.which`-detected (monkeypatch `which`).
7. Each of the three target paths resolves to the documented file.

`monkeypatch.setattr(Path, "home", ...)` to a tmp dir so no real user
config is touched.

## Gate

Full `pytest` + `ruff check` + `ruff format --check` + `mypy src/`
before commit. Roadmap entry as item 30 in `openspec/project.md`
(v2.19 → 31). README MCP section: replace the manual snippet with "auto
-registered by `halyard init`; explicit `halyard install-mcp-<tool>`".
