# Proposal: v2.12 — Glass Cockpit Background Service

## Why

`halyard dashboard` required the user to keep a terminal window open. Closing
the terminal killed the dashboard. This made it unsuitable as a persistent
ambient display — users cannot bookmark a URL that changes on every restart,
and they cannot glance at the dashboard without first finding and running a
terminal command.

A background service makes the Glass Cockpit behave like a menubar app: always
on, always at the same URL, accessible from any browser tab.

## What changes

- Fix the default dashboard port to `7432` so the URL is always
  `http://localhost:7432` and can be bookmarked.
- Add `--project-dir` option to `halyard dashboard` so the server can be
  started with an explicit project path (required for background launch).
- Add `POST /api/start` and `POST /api/stop` endpoints so timers can be
  controlled from the browser without a terminal.
- Add Start/Stop form controls to the Active Project metric card.
- Add `halyard service install/uninstall/status` commands that manage a macOS
  LaunchAgent (`io.kormilo.halyard`) to run the dashboard at login.

## What stays the same

- `halyard dashboard` still works as a foreground command.
- `--port` override is still supported.
- No new runtime dependencies.
- Source of truth remains the plain-text project files.

## Out of scope

- Linux systemd service.
- Windows service.
- Multi-project service (one service instance per machine).
- Authentication or TLS (localhost only).

## Success criteria

- `halyard service install` writes the LaunchAgent plist and loads it.
- The dashboard is accessible at `http://localhost:7432` after login without
  any manual command.
- Clicking Stop in the Active Project card writes an `o` entry to the
  timeclock and clears the active state file.
- Clicking Start with a `client/project` slug writes an `i` entry and sets
  the active state file.
- `halyard service status` reports running/stopped and the URL.
