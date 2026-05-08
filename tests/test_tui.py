"""Tests for the optional Textual TUI."""

from __future__ import annotations

import asyncio
import builtins
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from halyard.ai_log import HEADER, AiSession, append_session
from halyard.cli import app

runner = CliRunner()


def _session(
    *,
    start: datetime | None = None,
    project: str = "acme:auth",
    tags: list[str] | None = None,
    cost_usd: float = 1.25,
) -> AiSession:
    start_time = start or datetime(2026, 5, 7, 10)
    return AiSession(
        start=start_time,
        end=start_time + timedelta(minutes=5),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost_usd,
        project=project,
        tags=tags or [],
    )


def test_tui_import_error_without_textual(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "halyard.tui.app":
            raise ImportError(
                "Textual is required for the interactive dashboard. Install it with:\n"
                "  pip install halyard[tui]"
            )
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 1
    assert "pip install halyard[tui]" in result.output


def test_session_store_load(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    (tmp_path / "ai-sessions.log").write_text(HEADER)
    append_session(tmp_path, _session(project="acme:auth"))

    store = SessionStore(tmp_path / "ai-sessions.log")
    store.load()

    assert len(store.sessions) == 1
    assert store.sessions[0].project == "acme:auth"


def test_session_store_filter_time_window(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    store = SessionStore(tmp_path / "ai-sessions.log")
    now = datetime(2026, 5, 7, 12)
    store.sessions = [
        _session(start=now),
        _session(start=now - timedelta(days=1), project="acme:old"),
    ]

    result = store.filter(time_window="today", now=now)

    assert [session.project for session in result] == ["acme:auth"]


def test_session_store_filter_branch(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(tags=["branch:main"]),
        _session(project="acme:feature", tags=["branch:feature"]),
    ]

    result = store.filter(time_window="all", branch="main")

    assert len(result) == 1
    assert result[0].project == "acme:auth"


def test_session_store_branches_sorted_by_recent(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(start=datetime(2026, 5, 7, 12), tags=["branch:feature"]),
        _session(start=datetime(2026, 5, 7, 10), tags=["branch:main"]),
        _session(start=datetime(2026, 5, 7, 9), tags=["branch:feature"]),
    ]

    assert store.branches() == ["feature", "main"]


def test_session_feed_shows_sessions(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.session_feed import SessionFeed

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [_session()]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            assert pilot.app.query_one(SessionFeed).session_count == 1

    asyncio.run(run())


def test_time_window_key_changes_window(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("d")
            assert pilot.app.time_window == "today"

    asyncio.run(run())


def test_project_toggle_key(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store, project_slug="acme:auth")
        async with app_instance.run_test() as pilot:
            await pilot.press("p")
            assert pilot.app.project_scope == "project"

    asyncio.run(run())


def test_feed_selection_moves_with_arrow_keys(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.session_feed import SessionFeed

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [
            _session(project="acme:first"),
            _session(project="acme:second"),
        ]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("down")
            assert pilot.app.selected_index == 1
            assert pilot.app.query_one(SessionFeed).selected_index == 1

    asyncio.run(run())


def test_enter_opens_project_detail(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.project_pane import ProjectPane

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [_session(project="acme:auth")]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("enter")
            pane = pilot.app.query_one(ProjectPane)
            assert pilot.app.detail_project == "acme:auth"
            assert "Project: acme:auth" in pane.last_rendered_text

    asyncio.run(run())


def test_project_detail_renders_budget_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("textual")
    from halyard.budget import ProjectBudget
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets import project_pane
    from halyard.tui.widgets.project_pane import ProjectPane

    monkeypatch.setattr(
        project_pane,
        "load_budgets",
        lambda: {"acme:auth": ProjectBudget(daily_usd=2.0, monthly_usd=10.0)},
    )

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [
            _session(
                start=datetime.now(),
                project="acme:auth",
                cost_usd=1.25,
            )
        ]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("enter")
            text = pilot.app.query_one(ProjectPane).last_rendered_text
            assert "$1.2500 / $2.0000" in text
            assert "$1.2500 / $10.0000" in text

    asyncio.run(run())


def test_project_detail_renders_missing_budget_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets import project_pane
    from halyard.tui.widgets.project_pane import ProjectPane

    monkeypatch.setattr(project_pane, "load_budgets", lambda: {})

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [_session(start=datetime.now(), project="acme:auth", cost_usd=1.25)]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("enter")
            text = pilot.app.query_one(ProjectPane).last_rendered_text
            assert "Today: $1.2500 / -  Month: $1.2500 / -" in text

    asyncio.run(run())


def test_escape_returns_from_project_detail(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [_session(project="acme:auth")]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("enter")
            assert pilot.app.detail_project == "acme:auth"
            await pilot.press("escape")
            assert pilot.app.detail_project is None

    asyncio.run(run())


def test_branch_modal_key_opens_selector(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.branch_modal import BranchModal

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [_session(tags=["branch:main"])]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("b")
            assert isinstance(pilot.app.screen, BranchModal)

    asyncio.run(run())


def test_branch_modal_selects_branch(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [_session(tags=["branch:main"])]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("b")
            await pilot.press("enter")
            assert pilot.app.branch_filter == "main"

    asyncio.run(run())


def test_escape_clears_branch_filter(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [_session(tags=["branch:main"])]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        app_instance.branch_filter = "main"
        async with app_instance.run_test() as pilot:
            await pilot.press("escape")
            assert pilot.app.branch_filter is None

    asyncio.run(run())


def test_help_key_opens_help_modal(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.help_modal import HelpModal

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("?")
            assert isinstance(pilot.app.screen, HelpModal)

    asyncio.run(run())


def test_help_escape_dismisses_modal(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.help_modal import HelpModal

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            await pilot.press("?")
            assert isinstance(pilot.app.screen, HelpModal)
            await pilot.press("escape")
            assert not isinstance(pilot.app.screen, HelpModal)

    asyncio.run(run())


def test_session_feed_highlights_new_arrival(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.session_feed import SessionFeed

    feed = SessionFeed()
    # old session at index 0 (selected, shows ">"), recent at index 1 (should show "+")
    old = _session(start=datetime(2026, 1, 1), project="acme:old")
    recent = _session(start=datetime.now() - timedelta(seconds=10))
    feed.render_sessions([old, recent], selected_index=0)
    assert "+" in feed.last_rendered_text


def test_session_feed_no_highlight_for_old_session(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.session_feed import SessionFeed

    feed = SessionFeed()
    old1 = _session(start=datetime(2026, 1, 1), project="acme:old1")
    old2 = _session(start=datetime(2026, 1, 2), project="acme:old2")
    feed.render_sessions([old1, old2], selected_index=0)
    assert "+" not in feed.last_rendered_text


def test_store_reload_after_log_rotation(tmp_path: Path) -> None:
    from halyard.ai_log import HEADER, append_session
    from halyard.tui.store import SessionStore

    log = tmp_path / "ai-sessions.log"
    log.write_text(HEADER)
    append_session(tmp_path, _session(project="acme:before"))

    store = SessionStore(log)
    store.load()
    assert len(store.sessions) == 1

    # simulate rotation: delete and recreate with new session
    log.unlink()
    log.write_text(HEADER)
    append_session(tmp_path, _session(project="acme:after"))

    # app's _watch_events does: clear, then store.load() if file exists
    store.sessions = []
    store._offset = 0
    if store.log_path.exists():
        store.load()

    assert len(store.sessions) == 1
    assert store.sessions[0].project == "acme:after"


def test_budget_pane_renders_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("textual")
    from halyard.budget import BudgetStatus
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets import budget_pane
    from halyard.tui.widgets.budget_pane import BudgetPane

    monkeypatch.setattr(
        budget_pane,
        "budget_status",
        lambda now=None: [
            BudgetStatus(
                slug="acme:auth",
                today_spend=5,
                today_limit=10,
                month_spend=20,
                month_limit=100,
            )
        ],
    )

    async def run() -> None:
        store = SessionStore(Path("missing.log"))
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            pane = pilot.app.query_one(BudgetPane)
            pane.render_budgets()
            assert "acme:auth" in pane.last_rendered_text

    asyncio.run(run())


def test_log_missing_on_mount_sets_flag(tmp_path: Path) -> None:
    """log_missing=True when the log file doesn't exist at startup."""
    pytest.importorskip("textual")
    from textual.widgets import Static as TStatic

    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")  # file does not exist
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            assert pilot.app.log_missing is True
            status = pilot.app.query_one("#status", TStatic)
            assert "Waiting for log file" in str(status.render())

    asyncio.run(run())


def test_log_present_on_mount_clears_flag(tmp_path: Path) -> None:
    """log_missing=False when the log file exists at startup."""
    pytest.importorskip("textual")
    from textual.widgets import Static as TStatic

    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    log = tmp_path / "ai-sessions.log"
    log.write_text("; empty\n")

    async def run() -> None:
        store = SessionStore(log)
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            assert pilot.app.log_missing is False
            status = pilot.app.query_one("#status", TStatic)
            assert "Waiting" not in str(status.render())

    asyncio.run(run())


def test_store_clears_sessions_on_log_deletion(tmp_path: Path) -> None:
    """Sessions are cleared and offset reset when the log file is deleted."""
    pytest.importorskip("textual")
    from halyard.tui.store import SessionStore

    log = tmp_path / "ai-sessions.log"
    s = AiSession(
        start=datetime(2026, 5, 7, 10, 0),
        end=datetime(2026, 5, 7, 10, 10),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
    )
    log.write_text(s.to_log_line() + "\n")

    store = SessionStore(log)
    store.load()
    assert len(store.sessions) == 1

    # simulate the deletion branch of _watch_events
    store.sessions = []
    store._offset = 0

    assert store.sessions == []
    assert store._offset == 0


# ---------------------------------------------------------------------------
# ProjectPane work-health section (v2.6)
# ---------------------------------------------------------------------------


def test_project_pane_health_shows_tool_stats() -> None:
    from halyard.ai_log import AiSession
    from halyard.tui.widgets.project_pane import ProjectPane

    sessions = [
        AiSession(
            start=datetime(2026, 5, 8, 10, 0),
            end=datetime(2026, 5, 8, 10, 30),
            tool="gemini-cli",
            model="gemini-2.0-flash",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.0012,
            project="acme:auth",
            tool_calls=15,
            tool_errors=2,
            wall_seconds=1800,
            code_added=30,
            code_removed=8,
            resume_command="gemini --resume abc123",
        )
    ]
    pane = ProjectPane()
    pane.render_project("acme:auth", sessions)

    text = pane.last_rendered_text
    assert "Work Health" in text
    assert "15" in text
    assert "2" in text
    assert "+30" in text
    assert "-8" in text
    assert "gemini --resume abc123" in text


def test_project_pane_health_no_telemetry() -> None:
    from halyard.ai_log import AiSession
    from halyard.tui.widgets.project_pane import ProjectPane

    sessions = [
        AiSession(
            start=datetime(2026, 5, 8, 10, 0),
            end=datetime(2026, 5, 8, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.005,
            project="acme:auth",
        )
    ]
    pane = ProjectPane()
    pane.render_project("acme:auth", sessions)

    assert "No tool telemetry captured yet" in pane.last_rendered_text
