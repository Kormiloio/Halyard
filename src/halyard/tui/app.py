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
from halyard.tui.widgets.project_pane import ProjectPane
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
        ("?", "open_help_modal", "help"),
        ("up", "move_selection(-1)", "up"),
        ("down", "move_selection(1)", "down"),
        ("enter", "open_project_detail", "detail"),
        ("escape", "escape", "back"),
        ("q", "quit", "quit"),
    ]

    time_window: reactive[TimeWindow] = reactive("month")
    project_scope: reactive[ProjectScope] = reactive("hub")
    branch_filter: reactive[str | None] = reactive(None)
    detail_project: reactive[str | None] = reactive(None)
    log_missing: reactive[bool] = reactive(False)

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
        self.selected_index = 0
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(self._status_text(), id="status")
        with Horizontal(id="body"):
            with Vertical(id="main-pane"):
                yield SessionFeed(id="session-feed")
                yield ProjectPane(id="project-pane")
            with Vertical(id="side-pane"):
                yield BudgetPane(id="budget-pane")
                yield ModelPane(id="model-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.log_missing = not self.store.log_path.exists()
        self.store.load()
        self.refresh_views()
        self.run_worker(self._watch_and_refresh(), exclusive=True, thread=False)

    async def _watch_and_refresh(self) -> None:
        async for log_present in _watch_events(self.store):
            self.log_missing = not log_present
            self.refresh_views()

    def action_set_time_window(self, window: TimeWindow) -> None:
        self.time_window = window
        self.selected_index = 0
        self.detail_project = None
        self.refresh_views()

    def action_toggle_project_scope(self) -> None:
        self.project_scope = "project" if self.project_scope == "hub" else "hub"
        self.selected_index = 0
        self.detail_project = None
        self.refresh_views()

    def action_open_branch_modal(self) -> None:
        from halyard.tui.widgets.branch_modal import BranchModal

        branches = self.store.branches(self.active_sessions())
        self.push_screen(BranchModal(branches, self.branch_filter))

    def action_clear_branch_filter(self) -> None:
        if self.branch_filter is not None:
            self.branch_filter = None
            self.selected_index = 0
            self.detail_project = None
            self.refresh_views()

    def action_move_selection(self, delta: int) -> None:
        if self.detail_project is not None:
            return
        sessions = self.active_sessions()
        if not sessions:
            self.selected_index = 0
        else:
            self.selected_index = max(0, min(len(sessions) - 1, self.selected_index + delta))
        self.refresh_views()

    def action_open_project_detail(self) -> None:
        sessions = self.active_sessions()
        if not sessions:
            return
        selected = sessions[min(self.selected_index, len(sessions) - 1)]
        if selected.project is None:
            return
        self.detail_project = selected.project
        self.refresh_views()

    def action_escape(self) -> None:
        if self.detail_project is not None:
            self.detail_project = None
            self.refresh_views()
            return
        self.action_clear_branch_filter()

    def action_open_help_modal(self) -> None:
        from halyard.tui.widgets.help_modal import HelpModal

        self.push_screen(HelpModal())

    def on_branch_modal_branch_selected(self, message: BranchModal.BranchSelected) -> None:
        self.branch_filter = message.branch
        self.selected_index = 0
        self.detail_project = None
        self.refresh_views()

    def refresh_views(self) -> None:
        status = self.query_one("#status", Static)
        status.update(self._status_text())
        sessions = self.active_sessions()
        self._clamp_selection(sessions)
        feed = self.query_one(SessionFeed)
        detail = self.query_one(ProjectPane)
        if self.detail_project is None:
            feed.display = True
            detail.display = False
            feed.render_sessions(sessions, self.selected_index)
            pane_sessions = sessions
        else:
            feed.display = False
            detail.display = True
            project_sessions = [s for s in sessions if s.project == self.detail_project]
            detail.render_project(self.detail_project, project_sessions)
            pane_sessions = project_sessions
        self.query_one(ModelPane).render_sessions(pane_sessions)
        self.query_one(BudgetPane).render_budgets()

    def active_sessions(self) -> list[AiSession]:
        project = self.project_slug if self.project_scope == "project" else None
        return self.store.filter(
            time_window=self.time_window,
            project_scope=project,
            branch=self.branch_filter,
        )

    def _status_text(self) -> str:
        if self.log_missing:
            return f"  HALYARD  Waiting for log file: {self.store.log_path}"
        scope = "hub"
        if self.project_scope == "project":
            scope = f"project: {self.project_slug or 'unknown'}"
        parts = ["HALYARD", f"[{scope}]", f"[{self.time_window}]"]
        if self.branch_filter:
            parts.append(f"[branch: {self.branch_filter}]")
        if self.detail_project:
            parts.append(f"[detail: {self.detail_project}]")
        if self.header_note:
            parts.append(self.header_note)
        return "  ".join(parts)

    def _clamp_selection(self, sessions: list[AiSession]) -> None:
        if not sessions:
            self.selected_index = 0
            return
        self.selected_index = max(0, min(self.selected_index, len(sessions) - 1))


async def _watch_events(store: SessionStore) -> AsyncIterator[bool]:
    """Yield after log updates; isolated for tests and graceful no-watch fallback.

    Yields True when the log file is present, False when it was just deleted.
    """
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
            yield False
        else:
            if store.log_path.exists():
                store.read_new_lines()
            yield True
