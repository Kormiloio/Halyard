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

## Still Stuck

Run:

```bash
halyard doctor --json
```

Share the JSON output in a bug report. It should contain setup metadata only,
not prompts, transcripts, or source code.

