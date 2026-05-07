"""Tests for reusable AI reporting and dashboard health services."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.reports import build_ai_report, build_health_checks, read_active_timer


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
