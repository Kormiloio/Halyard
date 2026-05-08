# Design

## Command renaming

| Old name             | New canonical name        |
|----------------------|---------------------------|
| `install-hook`       | `install-hook-claude`     |
| `install-gemini-hook`| `install-hook-gemini`     |
| `install-cursor-hook`| `install-hook-cursor`     |

Old names are registered with `hidden=True` in Typer so they remain callable
but do not appear in `--help`.

## Auto-install on init

`halyard init` calls `_auto_install_detected_hooks()` after `scaffold_project()`.

Detection uses `shutil.which()` for each binary:

```
claude  → Claude Code hook (global ~/.claude/settings.json)
cursor  → Cursor hook (~/.cursor/hooks.json)
gemini  → Gemini CLI hook (~/.gemini/settings.json)
```

Each installer is wrapped in `try/except OSError` so a permission failure on
any single tool does not abort init.

Output printed at end of init:

```
Auto-installed hooks: Claude Code, Cursor
Not found on PATH: Gemini CLI ...
```

## Extracted private helpers

Each install command's logic is extracted into a private function so both the
CLI command and the auto-installer share the same code path:

- `_do_install_hook_claude(global_: bool)`
- `_do_install_hook_cursor()`
- `_do_install_hook_gemini()`
