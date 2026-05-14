"""Tests for reusable AI reporting and dashboard health services."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.reports import (
    build_ai_report,
    build_health_checks,
    build_human_time_report,
    format_minutes,
    parse_timeclock,
    read_active_timer,
    summarize_ai_sessions,
)


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / "time.timeclock").write_text("; time\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


def _session(project: str | None, cost: float = 1.0) -> AiSession:
    return AiSession(
        start=datetime(2026, 5, 7, 10, 0),
        end=datetime(2026, 5, 7, 10, 30),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=cost,
        project=project,
    )


def test_build_ai_report_groups_project_model_and_tool(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(tmp_path, _session("acme:auth", cost=2.0))
    append_session(tmp_path, _session("acme:auth", cost=3.0))

    report = build_ai_report(tmp_path, all_time=True)

    assert report.total_cost == 5.0
    assert report.total_input_tokens == 2000
    assert report.by_project[0].label == "acme:auth"
    assert report.by_project[0].sessions == 2
    assert report.by_model[0].label == "claude-sonnet-4-6"
    assert report.by_tool[0].label == "claude-code"


def test_build_ai_report_counts_unattributed_sessions(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(tmp_path, _session(None))

    report = build_ai_report(tmp_path, all_time=True)

    assert report.unattributed_count == 1
    assert report.by_project[0].label == "(unattributed)"


def test_health_checks_report_missing_hook(tmp_path: Path) -> None:
    _init_project(tmp_path)

    with patch("halyard.reports.Path.home", return_value=tmp_path / "home"):
        checks = build_health_checks(tmp_path)

    hook = next(check for check in checks if check.label == "Claude Code hook")
    assert hook.status == "warning"
    assert "install-hook" in hook.detail


def test_health_checks_detect_project_hook(tmp_path: Path) -> None:
    _init_project(tmp_path)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": "halyard cc-session"}]}
                    ],
                    "Stop": [{"hooks": [{"type": "command", "command": "halyard cc-hook"}]}],
                }
            }
        )
    )

    with patch("halyard.reports.Path.home", return_value=tmp_path / "home"):
        checks = build_health_checks(tmp_path)

    hook = next(check for check in checks if check.label == "Claude Code hook")
    assert hook.status == "healthy"


def test_health_checks_detect_hook_with_full_binary_path(tmp_path: Path) -> None:
    """Full absolute binary paths (uv tool installs) should be recognized as installed."""
    _init_project(tmp_path)
    home = tmp_path / "home"
    settings_dir = home / ".claude"
    settings_dir.mkdir(parents=True)
    uv_bin = "/Users/camaj/.local/share/uv/tools/halyard/bin"
    (settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"{uv_bin}/halyard cc-session",
                                }
                            ]
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"{uv_bin}/halyard cc-hook",
                                }
                            ]
                        }
                    ],
                }
            }
        )
    )

    with patch("halyard.reports.Path.home", return_value=home):
        checks = build_health_checks(tmp_path)

    hook = next(check for check in checks if check.label == "Claude Code hook")
    assert hook.status == "healthy"


def test_read_active_timer(tmp_path: Path) -> None:
    active = tmp_path / "active"
    active.write_text(
        "timeclock=/tmp/time.timeclock\nslug=acme:auth\nstarted=2026-05-07 10:00:00\n"
    )

    timer = read_active_timer(active)

    assert timer is not None
    assert timer.slug == "acme:auth"


def test_parse_timeclock_pairs_completed_and_open_entries(tmp_path: Path) -> None:
    timeclock = tmp_path / "time.timeclock"
    timeclock.write_text(
        "i 2026-05-07 09:00:00 acme:auth\no 2026-05-07 10:30:00\ni 2026-05-07 11:00:00 acme:auth\n"
    )

    entries = parse_timeclock(timeclock, now=datetime(2026, 5, 7, 11, 45))

    assert len(entries) == 2
    assert entries[0][2] == "acme:auth"
    assert int((entries[0][1] - entries[0][0]).total_seconds() // 60) == 90
    assert int((entries[1][1] - entries[1][0]).total_seconds() // 60) == 45


def test_build_human_time_report_summarizes_today_and_month(tmp_path: Path) -> None:
    _init_project(tmp_path)
    (tmp_path / "time.timeclock").write_text(
        "i 2026-05-07 09:00:00 acme:auth\n"
        "o 2026-05-07 10:30:00\n"
        "i 2026-05-06 09:00:00 globex:reports\n"
        "o 2026-05-06 10:00:00\n"
    )

    report = build_human_time_report(tmp_path, now=datetime(2026, 5, 7, 12, 0))

    assert report.today_minutes == 90
    assert report.month_minutes == 150
    assert report.by_project[0].label == "acme:auth"
    assert format_minutes(report.today_minutes) == "1h 30m"


# ---------------------------------------------------------------------------
# v2.30: by_tool_usage in AiReport
# ---------------------------------------------------------------------------


def _tool_session(
    tool: str,
    *,
    cost: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    tokens_available: bool = True,
) -> AiSession:
    return AiSession(
        start=datetime(2026, 5, 14, 10, 0),
        end=datetime(2026, 5, 14, 10, 30),
        tool=tool,
        model="claude-sonnet-4-6",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        tokens_available=tokens_available,
    )


def test_by_tool_usage_populated_with_session_counts() -> None:
    sessions = [
        _tool_session("claude-code", cost=1.0),
        _tool_session("claude-code", cost=2.0),
        _tool_session("codex", cost=0.0),
    ]
    report = summarize_ai_sessions(sessions, period_label="test")

    tools = {b.tool: b for b in report.by_tool_usage}
    assert tools["claude-code"].sessions == 2
    assert tools["codex"].sessions == 1


def test_by_tool_usage_zero_cost_tool_appears() -> None:
    """Codex (free tier) must appear even with $0 cost — the core v2.30 fix."""
    sessions = [
        _tool_session("claude-code", cost=5.0),
        _tool_session("codex", cost=0.0),
    ]
    report = summarize_ai_sessions(sessions, period_label="test")

    tool_names = [b.tool for b in report.by_tool_usage]
    assert "codex" in tool_names


def test_by_tool_usage_sorted_by_session_count_descending() -> None:
    sessions = [
        _tool_session("codex", cost=0.0),
        _tool_session("claude-code", cost=1.0),
        _tool_session("claude-code", cost=2.0),
    ]
    report = summarize_ai_sessions(sessions, period_label="test")

    assert report.by_tool_usage[0].tool == "claude-code"
    assert report.by_tool_usage[1].tool == "codex"


def test_by_tool_usage_aggregates_tokens() -> None:
    sessions = [
        _tool_session("claude-code", input_tokens=1000, output_tokens=200),
        _tool_session("claude-code", input_tokens=500, output_tokens=100),
    ]
    report = summarize_ai_sessions(sessions, period_label="test")

    bucket = report.by_tool_usage[0]
    assert bucket.tool == "claude-code"
    assert bucket.tokens == 1800


def test_by_tool_usage_session_share_sums_to_one() -> None:
    sessions = [
        _tool_session("claude-code"),
        _tool_session("codex"),
        _tool_session("cursor"),
    ]
    report = summarize_ai_sessions(sessions, period_label="test")

    total_share = sum(b.session_share for b in report.by_tool_usage)
    assert abs(total_share - 1.0) < 1e-9


def test_by_tool_usage_empty_sessions_returns_empty_list() -> None:
    report = summarize_ai_sessions([], period_label="test")
    assert report.by_tool_usage == []
