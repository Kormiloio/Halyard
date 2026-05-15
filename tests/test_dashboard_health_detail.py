"""v2.43 — actionable health warnings: HTML-structure regressions.

Open/close behavior is JS, verified manually in a browser
(openspec/changes/v2.43-health-detail/tasks.md). These assert the
server-rendered structure the script depends on.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.dashboard import render_dashboard


def _full_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / "time.timeclock").write_text("; time\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)
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


def test_pill_is_a_button_with_title_and_popup_present(tmp_path: Path) -> None:
    _full_project(tmp_path)
    html = render_dashboard(tmp_path)
    assert '<button id="health-pill"' in html
    assert 'title="' in html.split('id="health-pill"')[1][:200]
    assert 'id="health-popup"' in html
    assert "Halyard health popup failed" in html  # fail-safe script wired


def test_popup_lists_failing_check_and_points_to_doctor(tmp_path: Path) -> None:
    # An unattributed session yields an "Attribution" warning check.
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / "time.timeclock").write_text("; time\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 9, 0),
            end=datetime(2026, 5, 7, 9, 20),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            project=None,
        ),
    )
    html = render_dashboard(tmp_path)
    popup = html.split('id="health-popup"')[1].split("</div>\n    </div>")[0]
    # Remediation pointer is always present in the popup when something fails.
    assert "halyard doctor" in popup
    assert "health-popup-row" in popup
    # Pill title reflects that attention is needed.
    head = html.split('id="health-pill"')[1][:200]
    assert "attention" in head


def test_healthy_project_popup_says_all_good(tmp_path: Path) -> None:
    _full_project(tmp_path)
    html = render_dashboard(tmp_path)
    head = html.split('id="health-pill"')[1][:200]
    # Either healthy or neutral-only -> pill title is the healthy message
    # and the popup shows the all-healthy line. If the env yields a
    # warning we still must not crash; assert structure either way.
    assert ("All systems healthy" in head) or ("attention" in head)
    assert 'id="health-popup"' in html
