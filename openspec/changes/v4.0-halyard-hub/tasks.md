# Tasks: Halyard Hub (v4.0)

## Phase 1: Service Abstraction
- [x] 1.1 Create `ServiceProvider` base class in `src/halyard/service_manager.py`.
- [x] 1.2 Implement `LaunchdProvider` in `src/halyard/service_providers/launchd.py` (migrated from `service.py`).
- [x] 1.3 Implement `SystemdProvider` in `src/halyard/service_providers/systemd.py`.
- [x] 1.4 Implement `WindowsProvider` in `src/halyard/service_providers/windows.py`.
- [x] 1.5 Update `halyard service` CLI group to use the new manager.

## Phase 2: The Hub Daemon
- [x] 2.1 Implement `halyard hub start` command.
- [x] 2.2 Add OTLP/HTTP receiver to the Hub (reuse/expand `otel_receiver.py`).
- [x] 2.3 Implement the async write queue for `ai-sessions.log`.
- [x] 2.4 Detach `cache.db` synchronization to a background thread.

## Phase 3: Transition Collectors
- [x] 3.1 Update `append_session` to check if a Hub is running (via local ping).
- [x] 3.2 If Hub is active, `append_session` sends telemetry to Hub instead of writing directly.
- [x] 3.3 Ensure fallback to direct write if Hub is unreachable.

## Phase 4: Validation
- [x] 4.1 Add tests for concurrent emissions to the Hub.
- [x] 4.2 Verify Hub ingestion across all four primary collectors.
- [x] 4.3 Verify `halyard service` works on a simulated Linux unit test (using `mock`).

## Phase 5: Post-review fixes
- [x] 5.1 Restore service test coverage: the `_plist`/`PLIST_PATH`/`_installed_port`
      move broke `test_service.py`, `test_service_v218.py`, `test_plist_xml_injection.py`
      (2 collection errors + 8 failures). Rewrote all three to target `LaunchdProvider`.
- [x] 5.2 `SystemdProvider._unit_file` now quotes interpolated paths (`_sd_quote`) so a
      project dir with spaces/newlines can't break `ExecStart` arg-splitting or inject
      unit directives. (launchd already XML-escapes.)
- [x] 5.3 `LaunchdProvider.get_port` rejects non-dict plists and warns on malformed input
      instead of raising an uncaught `AttributeError`.
- [x] 5.4 `LaunchdProvider.uninstall` warns on non-zero `launchctl unload` (lost in refactor).
- [x] 5.5 `WindowsProvider.install`/`uninstall` raise `NotImplementedError` instead of
      returning a stub string the CLI printed as a success URL.
- [x] 5.6 `ServiceProvider.uninstall` now returns `bool`; `halyard service uninstall`
      prints "Service is not installed." when nothing was removed (API change — see design.md).
- [x] 5.7 Hub handler sets a 10s request timeout and verifies the full Content-Length body
      (slowloris / truncated-body hardening); `HubServer.port` now reflects the actually
      bound port (was stuck at the constructor value with ephemeral `port=0`).
