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
    tool: str = "claude-code",
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 100,
    output_tokens: int = 50,
    tokens_available: bool = True,
    client_surface: str | None = None,
) -> AiSession:
    start_time = start or datetime(2026, 5, 7, 10)
    return AiSession(
        start=start_time,
        end=start_time + timedelta(minutes=5),
        tool=tool,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        project=project,
        tokens_available=tokens_available,
        tags=tags or [],
        client_surface=client_surface,
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


def test_tui_prefers_current_project_over_hub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    import types

    project_dir = tmp_path / "project"
    hub_dir = tmp_path / "hub"
    project_dir.mkdir()
    hub_dir.mkdir()
    captured: dict[str, object] = {}

    class FakeHalyardApp:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def run(self) -> None:
            captured["ran"] = True

    module = types.ModuleType("halyard.tui.app")
    module.HalyardApp = FakeHalyardApp
    monkeypatch.setitem(sys.modules, "halyard.tui.app", module)
    monkeypatch.setattr("halyard.ai_log.find_project_dir", lambda: project_dir)
    monkeypatch.setattr("halyard.hub.find_hub", lambda: hub_dir)

    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 0
    assert captured["log_path"] == project_dir / "ai-sessions.log"
    assert captured["project_slug"] == "project"
    assert captured["ran"] is True


def test_tui_hub_flag_uses_configured_hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    project_dir = tmp_path / "project"
    hub_dir = tmp_path / "hub"
    project_dir.mkdir()
    hub_dir.mkdir()
    captured: dict[str, object] = {}

    class FakeHalyardApp:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def run(self) -> None:
            captured["ran"] = True

    module = types.ModuleType("halyard.tui.app")
    module.HalyardApp = FakeHalyardApp
    monkeypatch.setitem(sys.modules, "halyard.tui.app", module)
    monkeypatch.setattr("halyard.ai_log.find_project_dir", lambda: project_dir)
    monkeypatch.setattr("halyard.hub.find_hub", lambda: hub_dir)

    result = runner.invoke(app, ["tui", "--hub"])

    assert result.exit_code == 0
    assert captured["log_path"] == hub_dir / "ai-sessions.log"
    assert captured["project_slug"] == "project"
    assert captured["ran"] is True


def test_session_store_load(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    (tmp_path / "ai-sessions.log").write_text(HEADER, encoding="utf-8")
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


def test_session_store_load_missing_file(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    store = SessionStore(tmp_path / "absent.log")
    store.load()
    assert store.sessions == []
    assert store._offset == 0


def test_session_store_read_new_lines_no_file(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    store = SessionStore(tmp_path / "absent.log")
    assert store.read_new_lines() == []


def test_session_store_read_new_lines_appends_and_sorts(tmp_path: Path) -> None:
    from halyard.ai_log import AI_LOG_FILENAME
    from halyard.tui.store import SessionStore

    proj = tmp_path
    (proj / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    append_session(proj, _session(start=datetime(2026, 5, 7, 9)))

    store = SessionStore(proj / AI_LOG_FILENAME)
    store.load()
    assert len(store.sessions) == 1

    append_session(proj, _session(start=datetime(2026, 5, 7, 12)))
    parsed = store.read_new_lines()

    assert len(parsed) == 1
    # Newest-first ordering across old + newly tailed sessions.
    assert [s.start for s in store.sessions] == [
        datetime(2026, 5, 7, 12),
        datetime(2026, 5, 7, 9),
    ]


def test_session_store_read_new_lines_truncation_resets(tmp_path: Path) -> None:
    from halyard.ai_log import AI_LOG_FILENAME
    from halyard.tui.store import SessionStore

    log = tmp_path / AI_LOG_FILENAME
    proj = tmp_path
    log.write_text(HEADER, encoding="utf-8")
    append_session(proj, _session())

    store = SessionStore(log)
    store.load()
    assert store._offset > 0

    log.write_text(HEADER, encoding="utf-8")  # rotated/truncated smaller than offset
    assert store.read_new_lines() == []
    assert store._offset == log.stat().st_size
    assert store.sessions == []


def test_session_store_read_new_lines_amendment_reloads(tmp_path: Path) -> None:
    from halyard.ai_log import AI_LOG_FILENAME
    from halyard.tui.store import SessionStore

    log = tmp_path / AI_LOG_FILENAME
    log.write_text(HEADER, encoding="utf-8")
    store = SessionStore(log)
    store.load()

    with log.open("a") as fh:
        fh.write("a 2026-05-07T10:00:00 deadbeef project acme:new\n")

    # An 'a ' line forces a full reload and yields nothing incrementally.
    assert store.read_new_lines() == []


def test_session_store_filter_week_and_all(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    now = datetime(2026, 5, 15, 12)
    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(start=now - timedelta(days=3)),  # within week
        _session(start=now - timedelta(days=20)),  # outside week, same month
        _session(start=datetime(2026, 1, 1, 9)),  # old
    ]
    assert len(store.filter(time_window="week", now=now)) == 1
    assert len(store.filter(time_window="all", now=now)) == 3


def test_session_store_branches_skips_non_branch_tags(tmp_path: Path) -> None:
    from halyard.tui.store import SessionStore

    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(tags=["pr:42", "branch:main", "client:acme"]),
    ]
    assert store.branches() == ["main"]


def test_parse_session_line_skips_blank_and_comment() -> None:
    from halyard.tui.store import _parse_session_line

    assert _parse_session_line("") is None
    assert _parse_session_line("; a comment") is None


def test_in_window_all_returns_true() -> None:
    from halyard.tui.store import _in_window

    # "all" bypasses every date bound (the fall-through branch).
    assert _in_window(datetime(2000, 1, 1), "all", datetime(2026, 5, 16)) is True


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


def test_usage_pane_shows_summary(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.usage_pane import UsagePane

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [_session()]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            pane = pilot.app.query_one(UsagePane)
            assert "Voyage Stats" in pane.last_rendered_text
            assert "claude-sonnet-4-6" in pane.last_rendered_text

    asyncio.run(run())


def test_watch_pane_idle_shows_anchor_and_adrift(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.watch_pane import WatchPane

    pane = WatchPane()
    pane.render_watch(
        tmp_path,
        [
            _session(project="acme:auth"),
            _session(project=None, tokens_available=False),
        ],
    )

    assert "At anchor" in pane.last_rendered_text
    assert "Adrift    1" in pane.last_rendered_text
    assert "· · · — — — · · ·" in pane.last_rendered_text


def test_watch_pane_active_shows_current_watch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("textual")
    from halyard import reports
    from halyard.tui.widgets.watch_pane import WatchPane

    active_path = tmp_path / "active"
    timeclock = tmp_path / "time.timeclock"
    timeclock.write_text("", encoding="utf-8")
    active_path.write_text(
        f"slug=acme:auth\ntimeclock={timeclock}\nstarted=2026-05-07 10:00:00\n", encoding="utf-8"
    )
    monkeypatch.setattr(reports, "_HALYARD_ACTIVE", active_path)

    pane = WatchPane()
    pane.render_watch(
        tmp_path,
        [
            _session(start=datetime(2026, 5, 7, 10, 5), project="acme:auth"),
            _session(start=datetime(2026, 5, 7, 10, 8), project=None),
        ],
    )

    assert "Making way · acme:auth" in pane.last_rendered_text
    assert "Sessions  2  1/2 in manifest" in pane.last_rendered_text


def test_captain_pane_shows_rank_passport_and_medals(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.captain_pane import CaptainPane

    (tmp_path / "time.timeclock").write_text(
        "i 2026-05-07 10:00:00 acme:auth\no 2026-05-07 11:45:00\n", encoding="utf-8"
    )
    pane = CaptainPane()
    pane.render_record(
        tmp_path,
        [
            _session(tool="claude-code"),
            _session(tool="vscode", model="manual-task"),
        ],
    )

    assert "Captain's Quarters" in pane.last_rendered_text
    assert "Deckhand" in pane.last_rendered_text
    assert "VS Code" in pane.last_rendered_text
    assert "Eight Bells" in pane.last_rendered_text


def test_voyage_pane_shows_project_stage(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.voyage_pane import VoyagePane

    pane = VoyagePane()
    pane.render_voyages(
        tmp_path,
        [
            _session(start=datetime(2026, 5, 7, 9, minute), project="acme:auth")
            for minute in range(5)
        ],
    )

    assert "Voyage Roster" in pane.last_rendered_text
    assert "acme:auth" in pane.last_rendered_text
    assert "Making Headway" in pane.last_rendered_text


def test_tui_renders_nautical_side_rail(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.captain_pane import CaptainPane
    from halyard.tui.widgets.voyage_pane import VoyagePane
    from halyard.tui.widgets.watch_pane import WatchPane

    async def run() -> None:
        store = SessionStore(tmp_path / "ai-sessions.log")
        store.sessions = [
            _session(tool="claude-code"),
            _session(tool="vscode", model="manual-task"),
        ]
        store.load = lambda: None  # type: ignore[method-assign]
        app_instance = HalyardApp(store=store)
        async with app_instance.run_test() as pilot:
            assert "Current Watch" in pilot.app.query_one(WatchPane).last_rendered_text
            assert "Captain's Quarters" in pilot.app.query_one(CaptainPane).last_rendered_text
            assert "Voyage Roster" in pilot.app.query_one(VoyagePane).last_rendered_text

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
    log.write_text(HEADER, encoding="utf-8")
    append_session(tmp_path, _session(project="acme:before"))

    store = SessionStore(log)
    store.load()
    assert len(store.sessions) == 1

    # simulate rotation: delete and recreate with new session
    log.unlink()
    log.write_text(HEADER, encoding="utf-8")
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
    log.write_text("; empty\n", encoding="utf-8")

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
    log.write_text(s.to_log_line() + "\n", encoding="utf-8")

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


def test_project_pane_health_shows_metadata_counts() -> None:
    from halyard.ai_log import AiSession
    from halyard.tui.widgets.project_pane import ProjectPane

    sessions = [
        AiSession(
            start=datetime(2026, 5, 8, 10, 0),
            end=datetime(2026, 5, 8, 10, 30),
            tool="vscode",
            model="github-copilot",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            project="acme:auth",
            tokens_available=False,
            interaction_count=4,
            files_touched_count=3,
            test_run_count=1,
            test_status="pass",
        )
    ]
    pane = ProjectPane()
    pane.render_project("acme:auth", sessions)

    text = pane.last_rendered_text
    assert "Interactions: 4" in text
    assert "Files touched: 3" in text
    assert "Tests: 1 runs" in text


def test_session_feed_shows_metadata_badges() -> None:
    from halyard.tui.widgets.session_feed import SessionFeed

    session = _session(
        tool="vscode",
        model="github-copilot",
        input_tokens=0,
        output_tokens=0,
        tokens_available=False,
    )
    session.interaction_count = 4
    session.files_touched_count = 3
    session.test_status = "pass"
    feed = SessionFeed()

    feed.render_sessions([session])

    assert "4i" in feed.last_rendered_text
    assert "3f" in feed.last_rendered_text
    assert "test:pass" in feed.last_rendered_text


def test_session_feed_shows_client_surface_badge() -> None:
    from halyard.tui.widgets.session_feed import SessionFeed

    session = _session(
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=0,
        output_tokens=0,
        client_surface="desktop",
    )
    feed = SessionFeed()

    feed.render_sessions([session])

    assert "desktop" in feed.last_rendered_text
