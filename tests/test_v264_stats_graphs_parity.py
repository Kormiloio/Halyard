"""v2.64 — Stats & Graphs Parity Surface.

Audit (design.md Phase 0) found the data layer already rich: only
`total_messages`/`message_data_missing_sessions` and per-day per-model
in/out (`DailyUsageBucket.model_io`) were genuinely missing; the rest
is presentation on existing `UsageAnalytics`. These tests lock the new
aggregates, the range-aware heatmap + legend, the real (non
-approximated) per-day-per-model chart, flavour-line gating, the moat
-protection invariant, and TUI information parity.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app
from halyard.dashboard import render_dashboard
from halyard.tui.widgets.usage_pane import UsagePane
from halyard.usage import build_usage_analytics

runner = CliRunner()


def _init(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "time.timeclock").write_text("; time\n", encoding="utf-8")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")


def _s(
    day: int,
    *,
    model: str = "claude-sonnet-4-6",
    inp: int = 1000,
    out: int = 500,
    project: str | None = "acme:auth",
    user_msgs: int | None = 2,
    asst_msgs: int | None = 3,
    breakdown: str | None = None,
) -> AiSession:
    return AiSession(
        start=datetime(2026, 5, day, 10, 0),
        end=datetime(2026, 5, day, 10, 30),
        tool="claude-code",
        model=model,
        input_tokens=inp,
        output_tokens=out,
        cost_usd=0.01,
        project=project,
        user_message_count=user_msgs,
        assistant_message_count=asst_msgs,
        model_breakdown=breakdown,
    )


# 1. total_messages / message_data_missing_sessions ---------------------------


def test_message_aggregate_mirrors_token_missing_pattern() -> None:
    sessions = [
        _s(2, user_msgs=2, asst_msgs=3),  # 5 messages
        _s(3, user_msgs=1, asst_msgs=None),  # 1 message (partial still counts)
        _s(4, user_msgs=None, asst_msgs=None),  # missing → excluded, counted
    ]
    summary = build_usage_analytics(sessions, range_key="all").summary
    assert summary.total_messages == 6
    assert summary.message_data_missing_sessions == 1
    # Absent counts are NOT faked as 0 in the total — same as tokens.
    assert summary.total_messages != 0 or summary.sessions == 0


# 2. per-day per-model in/out bucketing + range filter ------------------------


def test_daily_model_io_split_and_range_filter() -> None:
    sessions = [
        _s(2, model="claude-sonnet-4-6", inp=1000, out=200),
        _s(2, model="gemini-2.5-pro", inp=500, out=100),
        _s(9, model="claude-sonnet-4-6", inp=300, out=50),
    ]
    usage = build_usage_analytics(sessions, range_key="all")
    by_day = {d.day.isoformat(): d for d in usage.daily}
    d2 = by_day["2026-05-02"]
    assert d2.model_io["claude-sonnet-4-6"] == (1000, 200)
    assert d2.model_io["gemini-2.5-pro"] == (500, 100)
    d9 = by_day["2026-05-09"]
    assert d9.model_io["claude-sonnet-4-6"] == (300, 50)

    # Range filter: a 7d window ending 2026-05-03 excludes the 05-09 row.
    windowed = build_usage_analytics(sessions, range_key="7d", now=datetime(2026, 5, 3, 12, 0))
    days = {d.day.isoformat() for d in windowed.daily}
    assert "2026-05-09" not in days
    assert "2026-05-02" in days


# 3. heatmap: cell count, intensity buckets, legend ---------------------------


def test_heatmap_is_range_aware_with_legend(tmp_path: Path) -> None:
    _init(tmp_path)
    for day in (2, 5, 9):
        append_session(tmp_path, _s(day))
    html = render_dashboard(tmp_path, usage_range="7d")
    # Range-aware: 7d window → 7 day cells (+ 5 legend swatches l0..l4).
    assert html.count("usage-cell usage-l") >= 7
    assert "usage-heatmap-legend" in html
    for lvl in range(5):
        assert f"usage-l{lvl}" in html
    assert "less" in html and "more" in html


# 4. models time series uses REAL per-day-per-model data + % share legend -----


def test_models_chart_uses_real_io_and_share(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(2, model="claude-sonnet-4-6", inp=4000, out=1000))
    append_session(tmp_path, _s(2, model="gemini-2.5-pro", inp=1000, out=200))
    html = render_dashboard(tmp_path, usage_tab="models")
    # Real per-day-per-model tooltip states the true in/out, not a
    # window-wide approximation.
    assert "in 4.0k" in html or "in 4000" in html
    # Legend carries per-model in/out + % share.
    assert "out " in html and "%" in html


# 5. flavour line: dashboard only, never report/invoice -----------------------

_FLAVOUR = "not billable"


def test_flavour_line_on_dashboard_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(2, inp=200_000, out=50_000))

    dash = render_dashboard(tmp_path)
    assert _FLAVOUR in dash  # present on the dashboard stats panel

    monkeypatch.chdir(tmp_path)
    report = runner.invoke(app, ["report", "--all"])
    assert report.exit_code == 0
    assert _FLAVOUR not in report.output  # never on the trust-bearing report


def test_flavour_line_absent_when_no_tokens(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(2, inp=0, out=0, model="claude-unknown"))
    assert _FLAVOUR not in render_dashboard(tmp_path)


# 6. moat-protection regression ----------------------------------------------


def test_moat_panels_still_present_with_parity_surface(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(2, project="acme:auth"))
    html = render_dashboard(tmp_path)
    # Cost + project attribution must survive the parity surface.
    assert 'data-panel="moat"' in html
    assert 'data-panel="usage"' in html
    assert "acme:auth" in html
    assert "captured · moat" in html  # cost card retained, labelled moat


# 7. TUI information parity ---------------------------------------------------


def test_tui_usage_pane_shows_headline_figures() -> None:
    pane = UsagePane()
    pane.render_sessions(
        [_s(2, user_msgs=4, asst_msgs=6), _s(3, user_msgs=1, asst_msgs=1)],
        now=datetime(2026, 5, 3, 12, 0),
    )
    text = pane.last_rendered_text
    for token in ("Sessions", "Messages", "Tokens", "Active", "Streak", "Peak", "Favorite"):
        assert token in text
    # 4+6+1+1 = 12 messages surfaced.
    assert "12" in text
