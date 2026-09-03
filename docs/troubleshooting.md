# Troubleshooting Halyard Capture

This guide covers the common reasons Halyard might not show a captured AI
session.

## Start Here

Run:

```bash
halyard doctor
```

If you just installed hooks and ran an AI tool, use:

```bash
halyard doctor --first-capture
```

The doctor checks project setup, hub setup, hook installation, log health,
unattributed sessions, and quarantine state.

## No Halyard Project Found

Run `halyard init` in the directory where you want local files such as
`halyard.toml` and `ai-sessions.log` to live.

If you want Halyard to capture sessions from many repos into one place, configure
a hub:

```bash
halyard hub set /path/to/halyard-project
```

## Hooks Missing

For guided setup, run:

```bash
halyard setup
```

For non-interactive setup of all supported hooks, run:

```bash
halyard setup --all --yes
```

You can also install hooks manually for the tools you use:

Install hooks for the tools you use:

```bash
halyard install-hook          # Claude Code
halyard install-cursor-hook   # Cursor
halyard install-gemini-hook   # Gemini CLI
```

Then run:

```bash
halyard doctor
```

## Session Was Captured But Not Attributed

If Halyard could not find a project or hub when a hook fired, it preserves the
session in `~/.halyard/unattributed.log`.

Recover those sessions with:

```bash
halyard assign-unattributed
```

## Malformed Session Records

Malformed log lines are quarantined in `~/.halyard/quarantine.log` instead of
being silently ignored.

Check the current project log with:

```bash
halyard check-log
```

## Gemini CLI Sessions Missing Detail

Gemini CLI rich telemetry depends on the local Gemini history file. If the
history file is unavailable when the hook runs, Halyard falls back to the
lighter hook payload.

You can also import historical Gemini sessions:

```bash
halyard import-gemini
```

## VS Code Extension

### Halyard CLI Not Found

The extension runs `halyard record-session` via a shell subprocess. If it
reports that `halyard` cannot be found:

1. Confirm `halyard` is on your PATH: open a terminal and run `halyard --version`.
2. If you installed with `pipx`, make sure `~/.local/bin` (or the pipx bin dir)
   is in your shell's PATH.
3. Set **Halyard: Executable Path** in VS Code settings
   (`halyard.executablePath`) to the absolute path returned by `which halyard`.

### Sessions Not Recording

If the extension is running but no sessions appear in `ai-sessions.log`:

1. Open the VS Code Output panel, select **Halyard** from the channel list, and
   look for error messages from `record-session`.
2. Run `halyard doctor` to confirm a project or hub is configured. The extension
   records to whatever project or hub `halyard` resolves from the workspace root.
3. Check that the workspace folder is inside (or is) a Halyard project directory.
   If not, configure a hub: `halyard hub set /path/to/halyard-project`.

### Status Bar Not Showing

The **$(clock) Halyard** status bar item appears once the extension activates.
If it is missing:

1. Confirm the **Halyard** extension is installed and enabled (Extensions panel
   → search "Halyard").
2. Check that the status bar is not hidden for the item. Right-click the status
   bar and look for a hidden Halyard entry.
3. Reload the VS Code window: **Command Palette → Developer: Reload Window**.

### Recovery Prompt on Restart

When VS Code restarts with an unfinished Halyard session (e.g., after a crash),
the extension prompts: *"An unfinished Halyard work block was found. Record it
now?"* Choose **Record** to save the session with the observed duration, or
**Discard** to drop it. This prompt appears at most once per restart.

If the prompt appears repeatedly, check that `halyard record-session` is not
returning an error — see the **Halyard** Output channel for details.

### Metadata Captured by the Extension

The VS Code extension captures editing time, branch, and code delta (lines
added/removed). It does not capture conversation transcripts, prompts, or
interaction counts — those are unavailable from the VS Code extension API.
See [collector-coverage.md](collector-coverage.md) for the full field matrix.

## Still Stuck

Run:

```bash
halyard doctor --json
```

Share the JSON output in a bug report. It should contain setup metadata only,
not prompts, transcripts, or source code.
