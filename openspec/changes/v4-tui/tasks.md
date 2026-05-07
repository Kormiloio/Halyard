# Tasks: v4 — Textual Interactive Terminal Dashboard

## Spec & design
- [x] Write proposal.md (design decisions locked)
- [x] Write specs/tui.md
- [x] Write design.md

## `pyproject.toml` — optional dependency
- [ ] Add `[project.optional-dependencies]` section with `tui = ["textual>=0.60"]`
- [ ] Add `watchfiles` as a transitive expectation (already a Textual dep; verify)

## `src/halyard/tui/` — new sub-package

### Package skeleton
- [ ] Create `src/halyard/tui/__init__.py` — re-exports `HalyardApp`; raises
  `ImportError` with install instructions if `textual` is not importable
- [ ] Create `src/halyard/tui/formatters.py` — tool icons, cost formatting, color rules
  - `tool_icon(tool: str) -> str` — returns emoji/char for each tool slug
  - `cost_str(usd: float) -> str` — "$0.0042" format
  - `budget_css_class(spend: float, limit: float | None) -> str` — ok/warn/high/over

### `src/halyard/tui/store.py` — SessionStore
- [ ] Define `SessionStore` with `reactive` sessions list
- [ ] Implement `load(log_path)` — parse full log on startup using `parse_sessions()`
- [ ] Implement `watch_log()` async method — tail new lines using `watchfiles.awatch()`
  - Track byte offset; read only new lines on each change event
  - Parse with `AiSession.from_log_line()`; skip None (quarantine handled upstream)
  - Append valid sessions to reactive list; notify watchers
- [ ] Handle log file rotation: detect DELETED event, re-open at new path
- [ ] `filter(time_window, project_scope, branch) -> list[AiSession]` — pure filter
  function (does not mutate store)

### `src/halyard/tui/widgets/session_feed.py`
- [ ] `SessionFeed(Widget)` — scrollable list of session rows
- [ ] Reactive on store sessions + active filters
- [ ] Each row: tool icon, model (truncated), project, duration, tokens, cost
- [ ] Newest sessions at top; new arrivals briefly highlighted
- [ ] `Enter` on a row: post `ProjectSelected(slug)` message to app

### `src/halyard/tui/widgets/project_pane.py`
- [ ] `ProjectPane(Widget)` — project detail view (shown on drill-down)
- [ ] Sessions list filtered to selected project
- [ ] Per-model cost breakdown bar chart (ASCII bars via Textual `ProgressBar`)
- [ ] Today's and month-to-date spend vs budget limits
- [ ] `Escape` returns to session feed

### `src/halyard/tui/widgets/budget_pane.py`
- [ ] `BudgetPane(Widget)` — spend vs limits for all configured projects
- [ ] Reads `load_budgets()` and `_sum_api_spend()` from `halyard.budget`
- [ ] Color classes: `budget-ok`, `budget-warn`, `budget-high`, `budget-over`
- [ ] "No budgets set" message when `load_budgets()` is empty

### `src/halyard/tui/widgets/model_pane.py`
- [ ] `ModelPane(Widget)` — cost by model bar chart
- [ ] Reactive on store + active time window
- [ ] Each row: model name, session count, cost, % of total

### `src/halyard/tui/widgets/branch_modal.py`
- [ ] `BranchModal(ModalScreen)` — branch selector overlay
- [ ] Lists all unique branch names from `branch:` tags in active sessions,
  sorted by most recent session
- [ ] Arrow keys + Enter to select; Escape to dismiss without change
- [ ] Posts `BranchSelected(branch)` message to app on selection

### `src/halyard/tui/app.py` — HalyardApp
- [ ] `HalyardApp(App)` with reactive: `time_window`, `project_scope`, `branch_filter`
- [ ] `on_mount()`: start `store.watch_log()` as background worker
- [ ] Layout: Header, SessionFeed + ProjectPane (tabbed), BudgetPane + ModelPane
  (side panel), Footer with key hints
- [ ] Key bindings: `d`, `w`, `m`, `a` (time window); `p` (project toggle);
  `b` (branch modal); `?` (help); `q` / `ctrl+c` (quit)
- [ ] Handle `ProjectSelected` message: swap SessionFeed for ProjectPane
- [ ] Handle `BranchSelected` message: set `branch_filter`, update header
- [ ] `app.tcss` CSS file with budget color classes and layout rules

## `src/halyard/cli.py` — `halyard tui` command
- [ ] Add `tui` command
- [ ] Import guard: catch `ImportError` from `halyard.tui`, print install
  instruction, exit 1
- [ ] Resolve log path: hub if configured, else project dir, else empty state
- [ ] Instantiate `HalyardApp(log_path=...)` and call `app.run()`

## Tests (`tests/test_tui.py`)
- [ ] `test_tui_import_error_without_textual` — mock `ImportError` on
  `halyard.tui`, verify CLI exits 1 with install message
- [ ] `test_session_store_load` — store loads sessions from a temp log file
- [ ] `test_session_store_filter_time_window` — `filter(time_window="today")`
  returns only today's sessions
- [ ] `test_session_store_filter_branch` — `filter(branch="main")` returns
  only sessions tagged `branch:main`
- [ ] `test_session_feed_shows_sessions` — `App.run_test()` with mock store,
  verify session count in feed
- [ ] `test_time_window_key_changes_window` — `await pilot.press("d")` sets
  `time_window = "today"`
- [ ] `test_project_toggle_key` — `await pilot.press("p")` toggles scope
- [ ] `test_budget_pane_renders_limits` — BudgetPane shows correct spend/limit
  for mocked budget data

## Quality
- [ ] Run full test suite — all passing
- [ ] Run mypy — no new errors (`textual` stubs via `textual-stubs` or
  `py.typed`)
- [ ] Run ruff — no new errors
- [ ] Verify `pip install halyard` (no `[tui]`) does not pull in Textual
- [ ] Verify `pip install halyard[tui]` installs Textual and `halyard tui` launches
