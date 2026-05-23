# v2.44 — TUI Health Visibility: Design

## Health data

`HalyardApp._health_checks()` → `reports.build_health_checks(project_dir)`
where `project_dir = self.store.log_path.parent` (the same dir the panes
already use). Called lazily from `_status_text()` and the modal action;
no caching/state (the checks are cheap file-existence probes and the TUI
already does heavier work each refresh). Failing = status in
`{"warning", "error"}` (mirrors `_overall_health` on the web; `neutral`
is not failing).

## Status-bar indicator

`_status_text()` appends one chip when there are failing checks:
`[⚠ N issue(s) — press h]`. Nothing is appended when all healthy, so
the bar is unchanged in the common case. The chip text is built from a
trusted count only (no check-derived strings interpolated into the
status line — keeps the v2.38 markup-escaping invariant trivially).

## Health modal

New `HealthModal(ModalScreen[None])` in
`tui/widgets/health_modal.py`, mirroring `HelpModal`:

- constructed with the `list[HealthCheck]`,
- title "System Health",
- if none failing: "✓ All systems healthy.",
- else one line per failing check: `dot label — detail` (status dot
  glyph: ⚠ warning / ✖ error), rendered via `rich.text.Text` /
  escaped so a crafted slug/detail cannot inject Textual markup
  (consistent with the v2.38 TUI escaping pass),
- footer: "Run `halyard doctor` for full diagnostics and fixes.",
- `escape` / `h` closes (dismiss).

Binding: add `("h", "open_health_modal", "health")` to `BINDINGS`;
`action_open_health_modal` builds the checks and `push_screen`s the
modal. `h` is currently unbound.

## Tests

`tests/test_tui_health.py`:
- app whose project dir is missing `ai-sessions.log` → `_status_text()`
  contains the `⚠` chip and `press h`;
- healthy project → no `⚠` chip;
- `HealthModal` with a failing check renders the label + detail + the
  `halyard doctor` line; with none → "All systems healthy";
- `h` is in `HalyardApp.BINDINGS`.

Textual screens are exercised the same way `test_tui.py` exercises
widgets (direct construction / compose), not via a live terminal — this
is a TUI surface, so there is no browser step; pytest is the verification.

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
