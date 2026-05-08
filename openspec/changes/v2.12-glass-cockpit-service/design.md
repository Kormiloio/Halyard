# Design

## Fixed port

`DASHBOARD_PORT = 7432` in `dashboard.py`. The `run_dashboard` default and the
`halyard dashboard` CLI default both use this constant. Port `0` (random) is
still accepted via `--port` for testing.

## POST endpoints

`DashboardHandler` gains `do_POST`:

- `POST /api/start` — form body `project=client/project`. Validates slug
  format, checks no timer is already running, appends `i` line to
  `time.timeclock`, writes `~/.halyard/active`.
- `POST /api/stop` — no body. Reads active timer, appends `o` line, removes
  `~/.halyard/active`.
- Both redirect to `/` on completion (302).
- Both are no-ops (redirect only) if preconditions are not met, so accidental
  double-submission is safe.

## Timer controls in HTML

The Active Project metric card is replaced by `_timer_metric(active_timer)`:

- **No timer**: renders a `<form>` with a text input (placeholder
  `client/project`) and a green Start button.
- **Timer active**: renders a `<form>` with a full-width red Stop button
  showing the active slug.

## `service.py` module

```
PLIST_LABEL  = "io.kormilo.halyard"
PLIST_PATH   = ~/Library/LaunchAgents/io.kormilo.halyard.plist
LOG_PATH     = ~/Library/Logs/halyard-dashboard.log
```

`install_service(project_dir, port)`:
1. Resolves `halyard` executable via `shutil.which`.
2. Writes plist with `RunAtLoad=true`, `KeepAlive=true`.
3. Runs `launchctl load -w <plist>`.
4. Returns the dashboard URL.

`uninstall_service()`: runs `launchctl unload -w`, removes plist.

`service_status()`: runs `launchctl list io.kormilo.halyard`, returns
`(running: bool, message: str)`.

## CLI commands

```
halyard service install   [--port 7432]
halyard service uninstall
halyard service status
```

All three print a macOS-only error on non-Darwin platforms.
`install` resolves project dir via `find_project_dir()` or `find_hub()`.
