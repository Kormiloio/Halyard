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
