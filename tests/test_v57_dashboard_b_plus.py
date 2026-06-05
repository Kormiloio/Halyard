"""v5.7 — dashboard B+: Overview tab, tabs, on/off, attribution normalize.

Structural contracts for the new layer. The exhaustive panel/render assertions
live in test_dashboard*.py; this guards the B+ additions.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from freezegun import freeze_time

from halyard import dashboard as d
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.dashboard import render_dashboard


@pytest.fixture(autouse=True)
def _freeze_to_may_2026():
    # v5.14: pin wall clock so May-2026 fixtures survive build_ai_report's
    # current-month filter.
    with freeze_time("2026-05-15 12:00:00"):
        yield


def _init(tmp_path: Path) -> Path:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "time.timeclock").write_text("; t\n", encoding="utf-8")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    return tmp_path


def _render(tmp_path: Path) -> str:
    _init(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 16, 0),
            end=datetime(2026, 5, 7, 16, 20),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=2000,
            output_tokens=400,
            cost_usd=0.25,
            project="acme:auth",
        ),
        direct=True,
    )
    return render_dashboard(tmp_path)


# --- chart helpers -------------------------------------------------------- #


def test_svg_donut_renders() -> None:
    out = d._svg_donut([("a", 3.0, "#fff"), ("b", 1.0, "#000")], center_top="$4")
    assert out.startswith("<svg") and "stroke-dasharray" in out and "$4" in out


def test_svg_area_and_stacked_render() -> None:
    assert "<svg" in d._svg_area([1.0, 5.0, 2.0])
    assert "no data" in d._svg_area([])
    assert "sbar" in d._svg_stacked_bar([("x", 2, "#fff"), ("y", 1, "#000")])


# project canonicalization moved to attribution.canonical_project (v5.8);
# covered in tests/test_v58_project_aliases.py.


# --- Overview tab + tabs -------------------------------------------------- #


def test_overview_panels_present(tmp_path: Path) -> None:
    html = _render(tmp_path)
    for pid in (
        "ov-kpis",
        "ov-cost",
        "ov-models",
        "ov-trend",
        "ov-activity",
        "ov-projects",
        "ov-outcomes",
    ):
        assert f'data-panel="{pid}"' in html, f"missing Overview panel {pid}"
    assert "svg-donut" in html  # cost + model-mix donuts
    assert "svg-area" in html  # tokens trend
    assert "Where the money went" in html


def test_tab_bar_and_script(tmp_path: Path) -> None:
    html = _render(tmp_path)
    for tab in ("overview", "money", "sessions", "voyage", "health", "all"):
        assert f'data-tab="{tab}"' in html
    assert "HalyardApplyTabs" in html  # client-side tab filter
    assert 'class="tabbar"' in html


def test_panel_onoff_controls_present(tmp_path: Path) -> None:
    html = _render(tmp_path)
    assert 'id="panels-btn"' in html  # manage menu trigger
    assert 'id="panels-menu"' in html
    assert "lay-remove" in html  # per-panel hide button (added in _layout_script)
    assert "halyard-removed-v1" in html  # persisted hidden set


def test_real_gamification_panels_still_render(tmp_path: Path) -> None:
    # The icons concern: Captain's Quarters / Friends panels are the real ones.
    html = _render(tmp_path)
    assert 'data-panel="captains-quarters"' in html
    assert 'data-panel="friends"' in html
    assert "Passport" in html  # passport stamps section (real panel)
