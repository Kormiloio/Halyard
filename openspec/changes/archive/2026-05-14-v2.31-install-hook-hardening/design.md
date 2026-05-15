# Design: v2.31 — Install-Hook Hardening

## Cross-file dedup

`_do_install_hook_claude()` currently reads one settings file, checks whether
the hook command is already in that file's entries, and skips the write if
found. The fix extends the check to also read the other file.

```python
def _do_install_hook_claude(global_: bool = False) -> None:
    target_path = (
        Path.home() / ".claude" / "settings.json"
        if global_
        else Path.cwd() / ".claude" / "settings.json"
    )
    other_path = (
        Path.cwd() / ".claude" / "settings.json"
        if global_
        else Path.home() / ".claude" / "settings.json"
    )
    ...
    # Before writing, check other_path for the same hook command.
    # If found, print a warning and return without writing.
```

The warning message must tell the user exactly where the hook already lives so
they can make an informed decision:

```
[yellow]Hook already present in {other_path} — skipping install.[/]
If you want the hook in both places, edit {target_path} manually.
```

The check uses the existing `_cmd_key()` normalizer so absolute-path
differences (`/usr/local/bin/halyard` vs `/home/user/.local/bin/halyard`) do
not create false negatives.

---

## Setup wizard scope question

In the `halyard setup` wizard, after the user confirms Claude Code as a tool,
insert a prompt before calling `_do_install_hook_claude()`:

```
Do you work on more than one project? [y/N]
```

- **Yes** → call `_do_install_hook_claude(global_=True)`, print a note:
  "Installed globally — all Claude Code sessions will be captured regardless
  of working directory."
- **No / Enter** → call `_do_install_hook_claude(global_=False)`, print a note:
  "Installed for this project. To capture other projects later, run
  `halyard install-hook --global-claude`."

If running non-interactively (no TTY), default to local install (existing
behavior) and skip the prompt.

---

## `halyard doctor` duplicate detection

Add a check to the doctor output: read both settings files, extract all hook
commands using `_cmd_key()`, and flag any command that appears in both.

Output when duplicates detected:
```
[WARN] Claude Code hook registered in both local and global settings.
       Sessions will be recorded twice. Fix: remove hooks from one file.
       Local:  .claude/settings.json
       Global: ~/.claude/settings.json
```

The doctor check is read-only — it reports but does not auto-fix.

---

## No migration, no data repair

This changeset does not touch existing `ai-sessions.log` files. Users who
already have duplicate session records need to address them separately.
The doctor warning gives them enough information to act.
