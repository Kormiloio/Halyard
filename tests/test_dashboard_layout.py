"""v2.42 — customizable dashboard layout: HTML-structure regressions.

Behavioral drag/collapse/persistence is JS and is verified manually in a
browser (see openspec/changes/v2.42-dashboard-layout/tasks.md). These
tests assert the structural contract the JS depends on.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.dashboard import render_dashboard

# Every panel + metric the layout script must be able to target.
_EXPECTED_PANELS = {
    # v5.7 Overview tab (new hero charts)
    "ov-kpis",
    "ov-cost",
    "ov-models",
    "ov-trend",
    "ov-activity",
    "ov-projects",
    "ov-outcomes",
    # metrics row
    "timer",
    "human-time",
    "ai-sessions",
    "ai-cost",
    # helper panels
    "voyage",
    "captains-quarters",
    "friends",
    # moat surface (v2.66) — ranks above commodity Usage
    "moat",
    # inline grid panels
    "usage",
    "leverage",
    "sessions",
    "health",
    "adrift",
    "collisions",
    "wake",
    "timeclock",
    "projects",
    "models",
    "tools",
    "budget",
    "costs",
}


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / "time.timeclock").write_text("; time\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


def _render(tmp_path: Path) -> str:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.01,
            project="acme:auth",
        ),
    )
    return render_dashboard(tmp_path)


def test_every_panel_has_a_stable_id(tmp_path: Path) -> None:
    html = _render(tmp_path)
    found = set(re.findall(r'data-panel="([a-z-]+)"', html))
    missing = _EXPECTED_PANELS - found
    assert not missing, f"panels missing data-panel: {missing}"


def test_panel_ids_are_unique(tmp_path: Path) -> None:
    html = _render(tmp_path)
    ids = re.findall(r'data-panel="([a-z-]+)"', html)
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate data-panel ids: {dupes}"
    assert len(ids) == len(_EXPECTED_PANELS)


def test_layout_script_present(tmp_path: Path) -> None:
    html = _render(tmp_path)
    assert "halyard-layout-order-v1" in html
    assert "halyard-layout-collapsed-v1" in html
    # Fail-safe wrapper so a JS error never blanks the dashboard.
    assert "Halyard layout script failed" in html


def test_reset_control_and_css_present(tmp_path: Path) -> None:
    html = _render(tmp_path)
    assert 'id="layout-reset"' in html
    assert ".is-collapsed" in html
    assert ".lay-handle" in html


def test_universal_toggle_and_metric_control_placement(tmp_path: Path) -> None:
    html = _render(tmp_path)
    # Master collapse/expand-all control at the top of the page.
    assert 'id="layout-toggle-all"' in html
    assert "expand all" in html
    # Metric controls pinned to the card's top-right corner.
    assert ".metric > .lay-controls { position: absolute;" in html


def test_drag_constrained_to_same_container(tmp_path: Path) -> None:
    # The script must check parentElement equality before reordering.
    html = _render(tmp_path)
    assert "src.parentElement !== el.parentElement" in html
