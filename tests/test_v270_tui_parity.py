"""v2.70 — TUI ↔ web dashboard parity.

Pane correctness lives in rendered text (no Pilot); one wiring smoke
uses run_test like the existing UsagePane test. The leverage-parity
case proves the TUI pane and the web `_leverage_panel` derive identical
numbers from the same sessions (single source of truth).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import HEADER, AiSession
from halyard.leverage import summarize

_NOW = datetime(2026, 5, 16, 12, 0, 0)
_MON = datetime(2026, 5, 11, 9, 0, 0)


def _s(
    project: str | None,
    *,
    attr: str | None = "timer",
    cost: float = 1.0,
    start: datetime = _MON,
    pr_state: str | None = None,
    remote: str | None = None,
) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=3),
        tool="claude-code",
        model="claude-opus-4-7",
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost,
        project=project,
        attr_method=attr,
        pr_state=pr_state,
        remote=remote,
    )


def test_moat_pane_renders_client_cost_evidence_and_no_markup_leak() -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.moat_pane import MoatPane

    pane = MoatPane()
    pane.render_sessions(
        [
            _s(project="acme:web", cost=3.0, pr_state="merged"),
            _s(project="acme:web", cost=1.0, pr_state="open"),
            _s(project="beta:api", cost=2.0, attr="git"),
        ],
        None,
        _NOW,
    )
    text = pane.last_rendered_text
    assert "acme:web" in text
    assert "$3" in text or "$4" in text  # cost-by-client total surfaces
    assert "shipped 1/2" in text  # billable evidence join
    assert "[" not in text  # no Rich markup leaked into the rendered text


def test_moat_pane_shows_leakage_with_exact_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets import moat_pane

    adrift = tmp_path / "unattributed.log"
    with adrift.open("w", encoding="utf-8") as fh:
        fh.write(HEADER)
        fh.write(_s(project=None, attr=None, remote="git@github.com:acme/web.git").to_log_line())
        fh.write("\n")
    monkeypatch.setattr(moat_pane, "unattributed_log_path", lambda: adrift)

    pane = moat_pane.MoatPane()
    pane.render_sessions([_s(project="acme:web", cost=1.0)], None, _NOW)
    text = pane.last_rendered_text
    assert "Leakage" in text
    assert "git@github.com:acme/web.git" in text
    assert "halyard link-repo client:" in text  # the exact one-command fix


def test_leverage_pane_shows_shipped_pct_and_buckets() -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.leverage_pane import LeveragePane

    sessions = [
        _s(project="a:b", pr_state="merged", start=_NOW - timedelta(days=1)),
        _s(project="a:b", pr_state="merged", start=_NOW - timedelta(days=2)),
        _s(project="a:b", pr_state="open", start=_NOW - timedelta(days=3)),
        _s(project="a:b", pr_state=None, start=_NOW - timedelta(days=4)),
    ]
    pane = LeveragePane()
    pane.render_sessions(sessions, _NOW)
    text = pane.last_rendered_text
    assert "Shipped 50%" in text
    assert "Merged     2" in text
    assert "Unsynced   1" in text


def test_leverage_parity_pane_matches_web_panel() -> None:
    """Single source of truth: web _leverage_panel and the pane agree."""
    pytest.importorskip("textual")
    from halyard.dashboard import _leverage_panel
    from halyard.tui.widgets.leverage_pane import LeveragePane

    sessions = [
        _s(project="a:b", pr_state="merged", start=_NOW - timedelta(days=1)),
        _s(project="a:b", pr_state="open", start=_NOW - timedelta(days=2)),
        _s(project="a:b", pr_state="closed", start=_NOW - timedelta(days=3)),
    ]
    summary = summarize(sessions, _NOW)

    web = _leverage_panel(sessions, _NOW)
    assert f"{summary.pct}%" in web
    assert f"<strong>{summary.merged}</strong> of <strong>{summary.total}</strong>" in web

    pane = LeveragePane()
    pane.render_sessions(sessions, _NOW)
    assert f"Shipped {summary.pct}%" in pane.last_rendered_text
    assert f"({summary.merged} of {summary.total} in merged PRs)" in pane.last_rendered_text


def test_panes_render_clean_empty_state() -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.leverage_pane import LeveragePane
    from halyard.tui.widgets.moat_pane import MoatPane

    moat = MoatPane()
    moat.render_sessions([], None, _NOW)
    assert "No sessions in view." in moat.last_rendered_text

    lev = LeveragePane()
    lev.render_sessions([], _NOW)
    assert "No sessions in the last 30 days." in lev.last_rendered_text


def test_moat_pane_preserves_confidence_labels_not_flattened() -> None:
    pytest.importorskip("textual")
    from halyard.tui.widgets.moat_pane import MoatPane

    pane = MoatPane()
    pane.render_sessions(
        [
            _s(project="acme:web", attr="timer"),
            _s(project="acme:web", attr=None),  # adrift band
        ],
        None,
        _NOW,
    )
    text = pane.last_rendered_text
    assert "timer" in text  # confidence band preserved, not collapsed
    assert "conf timer" in text  # per-project evidence keeps the band


def test_app_wiring_includes_both_panes(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    import asyncio

    from halyard.tui.app import HalyardApp
    from halyard.tui.store import SessionStore
    from halyard.tui.widgets.leverage_pane import LeveragePane
    from halyard.tui.widgets.moat_pane import MoatPane

    log = tmp_path / "ai-sessions.log"
    with log.open("w", encoding="utf-8") as fh:
        fh.write(HEADER)
        fh.write(_s(project="acme:web", pr_state="merged").to_log_line())
        fh.write("\n")

    async def _run() -> None:
        store = SessionStore(log)
        app = HalyardApp(store=store)
        # Small viewport so the stacked side-pane overflows and the
        # scroll-to-moat binding has something to do.
        async with app.run_test(size=(80, 20)) as pilot:
            moat = pilot.app.query_one(MoatPane)
            lev = pilot.app.query_one(LeveragePane)
            assert moat.id == "moat-pane"
            assert lev.id == "leverage-pane"
            assert moat.last_rendered_text
            assert lev.last_rendered_text

            side = pilot.app.query_one("#side-pane")
            assert side.allow_vertical_scroll  # container must be scrollable
            await pilot.press("o")
            await pilot.pause()
            # `o` scrolls the moat pane into view; with the panes above
            # it that means a non-zero vertical scroll offset.
            assert side.scroll_offset.y > 0

    asyncio.run(_run())
