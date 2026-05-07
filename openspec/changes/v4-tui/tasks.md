# Tasks: v4 — Textual Interactive Terminal Dashboard

## Spec & design
- [x] Write proposal.md (design decisions locked)
- [x] Write specs/tui.md
- [x] Write design.md

## `pyproject.toml` — optional dependency
- [x] Add `[project.optional-dependencies]` section with `tui = ["textual>=0.60"]`
- [x] Add `watchfiles` explicitly to the `tui` extra after verifying Textual does
  not install it transitively

## `src/halyard/tui/` — new sub-package

### Package skeleton
- [x] Create `src/halyard/tui/__init__.py` — re-exports `HalyardApp`; raises
  `ImportError` with install instructions if `textual` is not importable
- [x] Create `src/halyard/tui/formatters.py` — tool icons, cost formatting, color rules
  - [x] `tool_icon(tool: str) -> str` — returns char for each tool slug
  - [x] `cost_str(usd: float) -> str` — "$0.0042" format
  - [x] `budget_css_class(spend: float, limit: float | None) -> str` — ok/warn/high/over

### `src/halyard/tui/store.py` — SessionStore
- [x] Define `SessionStore` with in-memory sessions list
- [x] Implement `load(log_path)` — parse full log on startup
- [x] Implement `watch_log()` async method — tail new lines using `watchfiles.awatch()`
  - [x] Track byte offset; read only new lines on each change event
  - [x] Parse with `AiSession.from_log_line()`; skip None (quarantine handled upstream)
  - [x] Append valid sessions to session list for app refresh
- [ ] Handle full log file rotation: detect DELETED event, re-open at new path
- [x] `filter(time_window, project_scope, branch) -> list[AiSession]` — pure filter
  function (does not mutate store)

### `src/halyard/tui/widgets/session_feed.py`
- [x] `SessionFeed(Widget)` — session list
- [x] Refreshes from store sessions + active filters
- [x] Each row: tool icon, model (truncated), project, duration, tokens, cost
- [x] Newest sessions at top
- [ ] New arrivals briefly highlighted
- [ ] `Enter` on a row: post `ProjectSelected(slug)` message to app

### `src/halyard/tui/widgets/project_pane.py`
- [ ] `ProjectPane(Widget)` — project detail view (shown on drill-down)
- [ ] Sessions list filtered to selected project
- [ ] Per-model cost breakdown bar chart (ASCII bars via Textual `ProgressBar`)
- [ ] Today's and month-to-date spend vs budget limits
- [ ] `Escape` returns to session feed

### `src/halyard/tui/widgets/budget_pane.py`
- [x] `BudgetPane(Widget)` — spend vs limits for all configured projects
- [x] Reads `budget_status()` from `halyard.budget`
- [x] Color classes: `budget-ok`, `budget-warn`, `budget-high`, `budget-over`
- [x] "No budgets set" message when no budgets are configured

### `src/halyard/tui/widgets/model_pane.py`
- [x] `ModelPane(Widget)` — cost by model bar chart
- [x] Refreshes from store + active time window
- [x] Each row: model name, session count, cost, % of total

### `src/halyard/tui/widgets/branch_modal.py`
- [x] `BranchModal(ModalScreen)` — branch selector overlay
- [x] Lists all unique branch names from `branch:` tags in active sessions,
  sorted by most recent session
- [x] Arrow keys + Enter to select; Escape clears/dismisses
- [x] Posts `BranchSelected(branch)` message to app on selection

### `src/halyard/tui/app.py` — HalyardApp
- [x] `HalyardApp(App)` with reactive: `time_window`, `project_scope`, `branch_filter`
- [x] `on_mount()`: start log watcher as background worker
- [x] Layout: Header/status, SessionFeed, BudgetPane + ModelPane side panel,
  Footer with key hints
- [x] Key bindings: `d`, `w`, `m`, `a` (time window); `p` (project toggle);
  `q` (quit)
- [x] Key binding: `b` (branch modal)
- [x] Key binding: `?` (help)
- [ ] Key binding: `ctrl+c` explicit quit
- [ ] Handle `ProjectSelected` message: swap SessionFeed for ProjectPane
- [x] Handle `BranchSelected` message: set `branch_filter`, update header
- [x] `app.tcss` CSS file with budget color classes and layout rules

## `src/halyard/cli.py` — `halyard tui` command
- [x] Add `tui` command
- [x] Import guard: catch `ImportError` from `halyard.tui`, print install
  instruction, exit 1
- [x] Resolve log path: hub if configured, else project dir, else empty state
- [x] Instantiate `HalyardApp(log_path=...)` and call `app.run()`

## Tests (`tests/test_tui.py`)
- [x] `test_tui_import_error_without_textual` — mock `ImportError` on
  `halyard.tui`, verify CLI exits 1 with install message
- [x] `test_session_store_load` — store loads sessions from a temp log file
- [x] `test_session_store_filter_time_window` — `filter(time_window="today")`
  returns only today's sessions
- [x] `test_session_store_filter_branch` — `filter(branch="main")` returns
  only sessions tagged `branch:main`
- [x] `test_session_feed_shows_sessions` — `App.run_test()` with mock store,
  verify session count in feed
- [x] `test_time_window_key_changes_window` — `await pilot.press("d")` sets
  `time_window = "today"`
- [x] `test_project_toggle_key` — `await pilot.press("p")` toggles scope
- [x] `test_budget_pane_renders_limits` — BudgetPane shows correct spend/limit
  for mocked budget data

## Quality
- [x] Run full test suite — all passing
- [x] Run mypy — no new errors (`textual` stubs via `textual-stubs` or
  `py.typed`)
- [x] Run ruff — no new errors
- [x] Verify package metadata keeps Textual out of base dependencies
- [x] Verify `pip install halyard[tui]` installs Textual/watchfiles and `halyard tui` launches
