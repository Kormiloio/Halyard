# Tasks

Implementation checklist for v2.12 — Glass Cockpit Background Service.

## 1. Fixed port

- [x] 1.1 Add `DASHBOARD_PORT = 7432` constant to `dashboard.py`.
- [x] 1.2 Use constant as default in `run_dashboard` and `halyard dashboard`.

## 2. Timer control endpoints

- [x] 2.1 Add `do_POST` to `DashboardHandler` for `/api/start`.
- [x] 2.2 Add `do_POST` to `DashboardHandler` for `/api/stop`.
- [x] 2.3 Both redirect to `/` on completion.

## 3. Timer controls in HTML

- [x] 3.1 Replace Active Project `_metric()` call with `_timer_metric()`.
- [x] 3.2 `_timer_metric` renders Start form when no timer is running.
- [x] 3.3 `_timer_metric` renders Stop button when timer is active.
- [x] 3.4 Add `.btn`, `.btn-start`, `.btn-stop`, `.timer-form`, `.timer-input`
      CSS classes.

## 4. `service.py` module

- [x] 4.1 Create `src/halyard/service.py`.
- [x] 4.2 Implement `install_service(project_dir, port)`.
- [x] 4.3 Implement `uninstall_service()`.
- [x] 4.4 Implement `service_status()`.

## 5. CLI commands

- [x] 5.1 Add `--project-dir` option to `halyard dashboard`.
- [x] 5.2 Add `service` Typer subapp.
- [x] 5.3 Add `halyard service install`.
- [x] 5.4 Add `halyard service uninstall`.
- [x] 5.5 Add `halyard service status`.

## 6. Documentation

- [ ] 6.1 Update README with `halyard service install` quickstart.
- [ ] 6.2 Add bookmark tip for `http://localhost:7432`.
