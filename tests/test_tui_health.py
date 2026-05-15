"""v2.44 — TUI health visibility regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

from halyard.ai_log import HEADER
from halyard.reports import HealthCheck


def _good_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / "time.timeclock").write_text("; t\n")
    (tmp_path / "ai-sessions.log").write_text(HEADER)


def test_status_bar_shows_chip_when_a_check_fails(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    # No ai-sessions.log in tmp_path → build_health_checks yields an error.
    store = SessionStore(tmp_path / "ai-sessions.log")
    app = HalyardApp(store=store)
    txt = app._status_text()
    assert "⚠" in txt
    assert "press h" in txt


def test_status_bar_clean_when_healthy(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore

    _good_project(tmp_path)
    store = SessionStore(tmp_path / "ai-sessions.log")
    app = HalyardApp(store=store)
    assert "⚠" not in app._status_text()


def test_health_binding_registered() -> None:
    pytest.importorskip("textual")
    from halyard.tui.app import HalyardApp

    keys = {(b.key if hasattr(b, "key") else b[0]) for b in HalyardApp.BINDINGS}
    assert "h" in keys


def test_health_modal_partitions_failing() -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.health_modal import HealthModal

    checks = [
        HealthCheck("Project", "healthy", "ok"),
        HealthCheck("AI session log", "error", "Missing ai-sessions.log"),
        HealthCheck("Timeclock", "neutral", "not started"),
        HealthCheck("Attribution", "warning", "3 adrift"),
    ]
    m = HealthModal(checks)
    labels = {c.label for c in m._failing}
    assert labels == {"AI session log", "Attribution"}


def test_health_modal_renders_detail_and_doctor_hint(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from textual.widgets import Static

    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.health_modal import HealthModal

    _good_project(tmp_path)
    store = SessionStore(tmp_path / "ai-sessions.log")
    store.load = lambda: None  # type: ignore[method-assign]
    store.sessions = []
    app = HalyardApp(store=store)

    async def run() -> None:
        async with app.run_test() as pilot:
            await pilot.app.push_screen(
                HealthModal([HealthCheck("Collector", "error", "boom [x]")])
            )
            await pilot.pause()
            texts = "\n".join(str(w.render()) for w in pilot.app.screen.query(Static))
            assert "Collector" in texts
            assert "halyard doctor" in texts
            # The bracketed text survives as literal content — it was
            # escaped, so Textual did not consume it as a [markup] tag.
            assert "boom [x]" in texts

    import asyncio

    asyncio.run(run())


def test_health_modal_healthy_message() -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.health_modal import HealthModal

    m = HealthModal([HealthCheck("Project", "healthy", "ok")])
    assert m._failing == []
