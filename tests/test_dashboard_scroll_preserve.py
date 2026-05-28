"""Scroll position is preserved across the dashboard's reloads.

The 7d/30d/All and Overview/Models controls are server-rendered links
that hard-reload and reset scroll to the top, so the page ships a
scroll-restoration script. Auto-update no longer uses a full-page
``<meta refresh>`` (v5.6) — it swaps the metrics/grid regions in place,
which preserves scroll without a navigation.
"""

from __future__ import annotations

from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, HEADER
from halyard.dashboard import render_dashboard


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (p / "time.timeclock").write_text("; t\n", encoding="utf-8")
    (p / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    return p


def test_dashboard_includes_scroll_preserve(tmp_path: Path) -> None:
    html = render_dashboard(_proj(tmp_path / "p"))
    assert "halyard-scroll-v1" in html
    assert "scrollRestoration" in html
    # restores from sessionStorage and saves on unload
    assert "sessionStorage.getItem(KEY)" in html
    assert "sessionStorage.setItem(KEY" in html
    assert "beforeunload" in html


def test_no_meta_refresh_uses_partial_swap(tmp_path: Path) -> None:
    # v5.6: the full-page <meta refresh> is gone; auto-update is an in-place
    # 10s timer that swaps the metrics/grid regions and re-applies layout.
    html = render_dashboard(_proj(tmp_path / "p"))
    assert 'http-equiv="refresh"' not in html
    assert "setInterval(refresh, 10000)" in html
    assert "getElementById(id)" in html  # region swap
    assert "HalyardApplyLayout" in html  # layout re-applied after swap
