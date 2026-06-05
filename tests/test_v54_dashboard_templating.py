"""v5.4: dashboard page shell extracted to a Jinja2 template.

These lock the refactor's invariants: the template ships in the package,
the environment is cached, and the chrome the template now owns (doctype,
shell, topbar controls, panel scaffolding, footer) is still present in the
rendered page. The exhaustive per-panel assertions live in test_dashboard.py
and friends — this file guards the templating seam itself.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from freezegun import freeze_time

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.dashboard import _TEMPLATE_DIR, _dashboard_template, render_dashboard


@pytest.fixture(autouse=True)
def _freeze_to_may_2026():
    # v5.14 (extended): this file's May-2026 fixtures + render_dashboard()
    # depend on build_ai_report's current-month filter, so they break the
    # moment the wall clock leaves May 2026. Pin it like the other nine
    # time-cliff files. Surfaced by the pre-release gate on 2026-06-05.
    with freeze_time("2026-05-15 12:00:00"):
        yield


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "time.timeclock").write_text("; time\n", encoding="utf-8")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")


def test_template_file_ships_in_package() -> None:
    template = _TEMPLATE_DIR / "dashboard.html.j2"
    assert template.exists(), f"missing packaged template: {template}"


def test_template_environment_is_cached() -> None:
    assert _dashboard_template() is _dashboard_template()


def test_rendered_page_keeps_template_owned_chrome(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 6, 13, 0),
            end=datetime(2026, 5, 6, 13, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=200,
            cost_usd=0.05,
            project="acme:auth",
        ),
        direct=True,
    )
    html = render_dashboard(tmp_path)

    # Document chrome the template now owns.
    assert html.startswith("<!doctype html>")
    assert 'lang="en"' in html
    assert "Halyard · The Bridge" in html
    assert '<main class="shell">' in html
    assert '<header class="topbar">' in html
    assert '<section class="metrics"' in html
    assert '<section class="grid"' in html
    assert html.rstrip().endswith("</html>")

    # Topbar controls and panel scaffolding the JS / tests depend on.
    for marker in (
        'id="brand-mark"',
        'id="layout-toggle-all"',
        'id="layout-reset"',
        'id="theme-toggle"',
        'id="health-pill"',
        'data-panel="usage"',
        'data-panel="sessions"',
        'data-hub-fragment="costs"',
        "Latest session:",
    ):
        assert marker in html, f"template dropped chrome marker: {marker}"

    # Pre-rendered fragments still flow through the template.
    assert "acme:auth" in html
    assert "claude-sonnet-4-6" in html
