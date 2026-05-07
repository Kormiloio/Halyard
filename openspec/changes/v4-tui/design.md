# Design: v4 — Textual Interactive Terminal Dashboard

## Stack

| Concern | Choice | Reason |
|---------|--------|--------|
| UI framework | [Textual](https://textual.textualize.io/) | Purpose-built for Python terminal UIs; reactive data model; CSS-like layout |
| File watching | `watchfiles` (already a Textual dependency) | Async-friendly; wraps `inotify`/`kqueue`/`ReadDirectoryChanges` |
| Optional extra | `pip install halyard[tui]` | `pyproject.toml: [project.optional-dependencies] tui = ["textual>=0.60"]` |
| Package layout | `src/halyard/tui/` sub-package | Keeps TUI code isolated; importable only when Textual is installed |

## Module layout

```
src/halyard/tui/
├── __init__.py        # re-exports HalyardApp
├── app.py             # HalyardApp(App) — root Textual application
├── store.py           # SessionStore — in-memory session state + file watcher
├── widgets/
│   ├── session_feed.py    # SessionFeed(Widget) — scrollable session list
│   ├── project_pane.py    # ProjectPane(Widget) — drill-down detail
│   ├── budget_pane.py     # BudgetPane(Widget) — spend vs limits
│   ├── model_pane.py      # ModelPane(Widget) — cost by model bar chart
│   └── branch_modal.py    # BranchModal(ModalScreen) — branch selector overlay
└── formatters.py      # Tool icons, cost formatting, colour rules
```

## State model: SessionStore

`SessionStore` holds the parsed `list[AiSession]` in memory and owns the
file-watcher task. It is reactive: Textual widgets subscribe to it and
re-render when it changes.

```python
class SessionStore:
    sessions: reactive[list[AiSession]]   # full session list, newest first
    log_path: Path
    _watcher_task: asyncio.Task

    async def watch_log(self) -> None:
        # Uses watchfiles.awatch() to tail the log file.
        # On change: re-reads only new lines (tracks byte offset).
        # Parses each new line with AiSession.from_log_line().
        # Appends valid sessions to self.sessions.
        # Invalid lines go to quarantine — never crash the TUI.
```

Re-reading new lines only (by tracking file offset) keeps the watcher O(new
lines) rather than O(full file) on every change.

## Application structure

```
HalyardApp
├── Header          (static: hub/project, active time window, branch filter)
├── TabbedContent
│   ├── SessionFeed     (reactive on store.sessions + active filters)
│   └── ProjectPane     (shown when a project row is focused + Enter pressed)
├── Horizontal
│   ├── BudgetPane      (reactive on store.sessions + budgets)
│   └── ModelPane       (reactive on store.sessions + active time window)
└── Footer          (key binding hints)
```

Modals: `BranchModal` overlays the full screen when `b` is pressed.

## Reactivity

Textual's reactive system handles all re-renders. The pattern:

1. `SessionStore.sessions` is a `reactive` attribute.
2. Widgets that depend on sessions use `watch_sessions()` callbacks.
3. Filter state (time window, project scope, branch) lives on `HalyardApp`
   as reactive attributes; widgets use `watch_*` on the app reference.
4. No manual `refresh()` calls needed — Textual handles invalidation.

## File watching

`watchfiles.awatch(log_path)` is an async generator that yields change events.
Textual runs an asyncio event loop, so the watcher runs as a background task
inside the app:

```python
async def on_mount(self) -> None:
    self.run_worker(self.store.watch_log(), exclusive=True)
```

When the log file is rotated (yearly rollover, future v5 feature), the watcher
detects the `DELETED` event and re-opens with the new path.

## Graceful degradation

If `textual` is not importable, `halyard/tui/__init__.py` raises `ImportError`
with a clear message. The `halyard tui` CLI command catches `ImportError` and
prints the install instruction before exiting 1. This is the only code path
that runs without Textual installed.

## CSS / styling

Textual uses its own CSS dialect (TCSS). Styles live in
`src/halyard/tui/app.tcss`. Budget status colours:

```css
.budget-ok      { color: green; }
.budget-warn    { color: yellow; }
.budget-high    { color: red; }
.budget-over    { color: red; text-style: blink; }
```

## Testing

Textual provides `App.run_test()` for async unit tests. The test pattern:

```python
async def test_session_feed_shows_new_session():
    app = HalyardApp(store=MockStore([_session()]))
    async with app.run_test() as pilot:
        assert pilot.app.query_one(SessionFeed).session_count == 1
```

Key dispatch tests:
```python
await pilot.press("d")   # time window → today
await pilot.press("p")   # toggle project scope
await pilot.press("b")   # open branch modal
```

## Trade-offs considered

**Why not Rich Live instead of Textual?**
Rich Live is what `halyard dashboard` uses. It is a one-way auto-refresh
display — no interactive navigation, no keyboard-driven drill-down. Textual is
the purpose-built upgrade path.

**Why not a web dashboard?**
Local-first is a non-negotiable. A browser tab requires a running server,
introduces a port, and is not composable with terminal workflows. The TUI runs
in the same terminal as the developer's work.

**Why in-memory and not SQLite?**
SQLite is the right answer at 100k+ sessions. At current scale (hundreds to low
thousands of sessions per project per month), parsing the full log on startup
takes under 100ms. Adding SQLite now would require a migration path, a schema
version, and a process to keep the DB in sync with the append-only log. The
log is the source of truth; any cache is derivative.
