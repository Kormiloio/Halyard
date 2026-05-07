"""Textual application for `halyard tui`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from halyard.ai_log import AI_LOG_FILENAME, AiSession
from halyard.tui.store import SessionStore, TimeWindow
from halyard.tui.widgets.budget_pane import BudgetPane
from halyard.tui.widgets.model_pane import ModelPane
from halyard.tui.widgets.session_feed import SessionFeed

if TYPE_CHECKING:
    from halyard.tui.widgets.branch_modal import BranchModal

ProjectScope = Literal["hub", "project"]


class HalyardApp(App[None]):
    """Interactive Halyard terminal dashboard."""

    CSS_PATH = "app.tcss"
    BINDINGS: ClassVar = [
        ("d", "set_time_window('today')", "today"),
        ("w", "set_time_window('week')", "week"),
        ("m", "set_time_window('month')", "month"),
        ("a", "set_time_window('all')", "all"),
        ("p", "toggle_project_scope", "project"),
        ("b", "open_branch_modal", "branch"),
        ("escape", "clear_branch_filter", "clear branch"),
        ("q", "quit", "quit"),
    ]

    time_window: reactive[TimeWindow] = reactive("month")
    project_scope: reactive[ProjectScope] = reactive("hub")
    branch_filter: reactive[str | None] = reactive(None)

    def __init__(
        self,
        *,
        log_path: Path | None = None,
        project_slug: str | None = None,
        header_note: str | None = None,
        store: SessionStore | None = None,
    ) -> None:
        resolved_log_path = log_path or Path.cwd() / AI_LOG_FILENAME
        self.store = store or SessionStore(resolved_log_path)
        self.project_slug = project_slug
        self.header_note = header_note
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(self._status_text(), id="status")
        with Horizontal(id="body"):
            with Vertical(id="main-pane"):
                yield SessionFeed(id="session-feed")
            with Vertical(id="side-pane"):
                yield BudgetPane(id="budget-pane")
                yield ModelPane(id="model-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.store.load()
        self.refresh_views()
        self.run_worker(self._watch_and_refresh(), exclusive=True, thread=False)

    async def _watch_and_refresh(self) -> None:
        before = len(self.store.sessions)
        async for _event in _watch_events(self.store):
            if len(self.store.sessions) != before:
                before = len(self.store.sessions)
                self.refresh_views()

    def action_set_time_window(self, window: TimeWindow) -> None:
        self.time_window = window
        self.refresh_views()

    def action_toggle_project_scope(self) -> None:
        self.project_scope = "project" if self.project_scope == "hub" else "hub"
        self.refresh_views()

    def action_open_branch_modal(self) -> None:
        from halyard.tui.widgets.branch_modal import BranchModal

        branches = self.store.branches(self.active_sessions())
        self.push_screen(BranchModal(branches, self.branch_filter))

    def action_clear_branch_filter(self) -> None:
        if self.branch_filter is not None:
            self.branch_filter = None
            self.refresh_views()

    def on_branch_modal_branch_selected(self, message: BranchModal.BranchSelected) -> None:
        self.branch_filter = message.branch
        self.refresh_views()

    def refresh_views(self) -> None:
        status = self.query_one("#status", Static)
        status.update(self._status_text())
        sessions = self.active_sessions()
        self.query_one(SessionFeed).render_sessions(sessions)
        self.query_one(ModelPane).render_sessions(sessions)
        self.query_one(BudgetPane).render_budgets()

    def active_sessions(self) -> list[AiSession]:
        project = self.project_slug if self.project_scope == "project" else None
        return self.store.filter(
            time_window=self.time_window,
            project_scope=project,
            branch=self.branch_filter,
        )

    def _status_text(self) -> str:
        scope = "hub"
        if self.project_scope == "project":
            scope = f"project: {self.project_slug or 'unknown'}"
        parts = ["HALYARD", f"[{scope}]", f"[{self.time_window}]"]
        if self.branch_filter:
            parts.append(f"[branch: {self.branch_filter}]")
        if self.header_note:
            parts.append(self.header_note)
        return "  ".join(parts)


async def _watch_events(store: SessionStore) -> AsyncIterator[None]:
    """Yield after log updates; isolated for tests and graceful no-watch fallback."""
    try:
        from watchfiles import Change, awatch
    except ImportError:
        return

    watch_root = store.log_path.parent if store.log_path.parent.exists() else Path.cwd()
    async for changes in awatch(watch_root):
        if not any(Path(path) == store.log_path for _change, path in changes):
            continue
        log_deleted = any(
            change == Change.deleted for change, path in changes if Path(path) == store.log_path
        )
        if log_deleted:
            store.sessions = []
            store._offset = 0
        else:
            store.read_new_lines()
        yield None
