"""Scroll position is preserved across the dashboard's reloads.

The 7d/30d/All and Overview/Models controls are server-rendered links
and a <meta refresh> hard-reloads every 10s; both reset scroll to the
top. The page must ship a scroll-restoration script so reading a
mid-page panel isn't interrupted.
"""

from __future__ import annotations

from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, HEADER
from halyard.dashboard import render_dashboard


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n")
    (p / "time.timeclock").write_text("; t\n")
    (p / AI_LOG_FILENAME).write_text(HEADER)
    return p


def test_dashboard_includes_scroll_preserve(tmp_path: Path) -> None:
    html = render_dashboard(_proj(tmp_path / "p"))
    assert "halyard-scroll-v1" in html
    assert "scrollRestoration" in html
    # restores from sessionStorage and saves on unload
    assert "sessionStorage.getItem(KEY)" in html
    assert "sessionStorage.setItem(KEY" in html
    assert "beforeunload" in html


def test_meta_refresh_still_present(tmp_path: Path) -> None:
    # The auto-refresh stays (scroll persistence is what makes it
    # non-disruptive); guard against accidentally removing it.
    html = render_dashboard(_proj(tmp_path / "p"))
    assert 'http-equiv="refresh"' in html
