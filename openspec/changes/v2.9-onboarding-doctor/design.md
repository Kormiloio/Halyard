# v2.9 Onboarding Doctor Design

## Command

```bash
halyard doctor [--json] [--first-capture] [--tool claude|cursor|gemini|all]
```

Default behavior prints a human-readable checklist. `--json` emits a stable
machine-readable result. `--first-capture` adds recency checks that help users
confirm a new AI session was captured.

## Health Model

Represent each check as:

```python
@dataclass(frozen=True)
class DoctorCheck:
    id: str
    label: str
    status: Literal["ok", "warning", "error", "skipped"]
    detail: str
    fix: str | None = None
```

The top-level report includes:

```python
@dataclass(frozen=True)
class DoctorReport:
    status: Literal["ok", "warning", "error"]
    checks: list[DoctorCheck]
```

Exit code:

- `0`: no `error` checks.
- `1`: one or more `error` checks.

Warnings are visible but do not fail the command.

## Checks

### Project

- Current directory is inside a Halyard project (`halyard.toml` found).
- `ai-sessions.log` exists.
- `ai-sessions.log` is writable.

If no project is found, the doctor should check for a hub and explain whether
ambient capture still has a destination.

### Hub

- `~/.halyard/hub` exists.
- The hub path exists.
- The hub contains `halyard.toml` and `ai-sessions.log`.

Hub absence is a warning inside a project and an error outside a project.

### Hooks

Read the same local config files as installers:

- Claude Code: `.claude/settings.json` and `~/.claude/settings.json`.
- Cursor: `~/.cursor/hooks.json`.
- Gemini CLI: `~/.gemini/settings.json`.

Check for the expected Halyard commands:

- `cc-session`, `cc-hook`;
- `cursor-session`, `cursor-hook`;
- `gc-session`, `gc-model`, `gc-hook`.

If a hook is missing, show the matching install command:

- `halyard install-hook`;
- `halyard install-cursor-hook`;
- `halyard install-gemini-hook`.

### Collector State

Check per-user runtime files where useful:

- `~/.halyard/unattributed.log` count;
- `~/.halyard/quarantine.log` existence;
- `~/.halyard/gc-session` existence and age;
- `~/.halyard/cursor-session` existence and age;
- `~/.halyard/active` active project timer.

The doctor should not delete, rewrite, or repair these files.

### First-Capture

`--first-capture` checks whether the destination log has a recent AI session.

Suggested behavior:

- Find the active project or hub destination.
- Parse `ai-sessions.log`.
- Look for sessions ending in the last 30 minutes.
- If none are found, check `~/.halyard/unattributed.log` for recent sessions.
- If none are found, check `~/.halyard/quarantine.log`.
- Print next steps based on which bucket has data.

This is not a synthetic test capture. It verifies that real collector output
arrived somewhere.

## Output

### Text

Text output should be compact and actionable:

```text
Halyard Doctor
OK      Project        /path/to/project
OK      AI log         ai-sessions.log writable
WARN    Hub            no hub configured
OK      Claude Code    hooks installed
ERROR   Gemini CLI     hooks missing
        fix: halyard install-gemini-hook
```

### JSON

```json
{
  "status": "warning",
  "checks": [
    {
      "id": "project.found",
      "label": "Project",
      "status": "ok",
      "detail": "/path/to/project",
      "fix": null
    }
  ]
}
```

JSON output must not include prompt content, transcript content, or source code.

## Module Layout

```text
src/halyard/doctor.py
tests/test_doctor.py
docs/troubleshooting.md
```

Keep `doctor.py` mostly pure functions so tests can use temporary home/project
directories without invoking real AI tools.

## Relationship To Existing Commands

`halyard doctor` does not replace:

- `halyard check-log`: validates log line syntax.
- `halyard dashboard`: shows live local activity.
- `halyard tui`: interactive terminal cockpit.
- `halyard assign-unattributed`: repairs unattributed captures.

Instead, `doctor` links to or recommends those commands when appropriate.

