"""Tests for v2.9 onboarding diagnostics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, AiSession
from halyard.cli import app
from halyard.doctor import _claude_hook_duplicate_check, build_doctor_report, render_json
from halyard.state_integrity import write_trusted_state


class MagicPathMock:
    """Mock for Path class that returns a fixed home() value."""

    def __init__(self, home: Path):
        self._home = home
        self._real_path = Path

    def __call__(self, *args, **kwargs):
        return self._real_path(*args, **kwargs)

    def home(self):
        return self._home

    def __getattr__(self, name):
        return getattr(self._real_path, name)


def _project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "halyard.toml").write_text("[project]\n", encoding="utf-8")
    (path / AI_LOG_FILENAME).write_text("; header\n", encoding="utf-8")
    return path


def _session(*, end: datetime, project: str | None = "acme:auth") -> AiSession:
    return AiSession(
        start=end - timedelta(minutes=10),
        end=end,
        tool="claude-code",
        model="claude-sonnet",
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.01,
        project=project,
    )


def _write_home_hub(home: Path, project_dir: Path, monkeypatch=None) -> None:  # type: ignore[no-untyped-def]
    state = home / ".halyard"
    state.mkdir(parents=True, exist_ok=True)
    (state / "hub").write_text(str(project_dir) + "\n", encoding="utf-8")
    # The conftest hub-pointer isolation (v5.23 follow-up) overrides the
    # home-based pointer; tests provisioning a fake-home hub must point the
    # override at it too, or find_hub() reads the empty isolation path.
    if monkeypatch is not None:
        monkeypatch.setattr("halyard.hub._HUB_POINTER", state / "hub")


def _write_claude_hooks(root: Path) -> None:
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": "/bin/halyard cc-session"}]}
                    ],
                    "Stop": [{"hooks": [{"type": "command", "command": "/bin/halyard cc-hook"}]}],
                }
            }
        ),
        encoding="utf-8",
    )


def _write_cursor_hooks(home: Path) -> None:
    settings = home / ".cursor" / "hooks.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "beforeSubmitPrompt": [{"command": "/bin/halyard cursor-session"}],
                    "stop": [{"command": "/bin/halyard cursor-hook"}],
                },
            }
        ),
        encoding="utf-8",
    )


def _write_gemini_hooks(home: Path) -> None:
    settings = home / ".gemini" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "telemetry": {
                    "enabled": True,
                    "target": "local",
                    "outfile": str(home / ".halyard" / "gemini-otel.log"),
                },
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "/bin/halyard gc-session"}]}
                    ],
                    "AfterModel": [
                        {"hooks": [{"type": "command", "command": "/bin/halyard gc-model"}]}
                    ],
                    "AfterAgent": [
                        {"hooks": [{"type": "command", "command": "/bin/halyard gc-hook"}]}
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def test_doctor_healthy_project(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    monkeypatch.setattr(Path, "home", lambda: home)
    _write_home_hub(home, project, monkeypatch)
    _write_claude_hooks(project)
    _write_cursor_hooks(home)
    _write_gemini_hooks(home)

    # v3.6: Mock Windsurf hook
    ws_hooks = home / ".codeium" / "windsurf" / "hooks.json"
    ws_hooks.parent.mkdir(parents=True, exist_ok=True)
    ws_hooks.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreUserPrompt": [{"command": "/bin/halyard windsurf-session-start"}],
                    "PostCascadeResponse": [{"command": "/bin/halyard windsurf-session-stop"}],
                }
            }
        ),
        encoding="utf-8",
    )

    report = build_doctor_report(start=project)

    # We expect 'ok' baseline integrations, but don't fail on environment-specific
    # warnings like Gemini telemetry or unwired history that vary by machine.
    assert report.status != "error"
    assert any(check.id == "project.found" and check.status == "ok" for check in report.checks)
    assert any(check.id == "hook.claude" and check.status == "ok" for check in report.checks)
    assert any(check.id == "hook.cursor" and check.status == "ok" for check in report.checks)
    assert any(check.id == "hook.gemini" and check.status == "ok" for check in report.checks)
    assert any(check.id == "hook.windsurf" and check.status == "ok" for check in report.checks)


def test_doctor_no_project_no_hub_errors(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)

    report = build_doctor_report(start=tmp_path / "empty")

    assert report.status == "error"
    assert any(check.id == "project.found" and check.status == "error" for check in report.checks)
    assert any(check.id == "hub.configured" and check.status == "error" for check in report.checks)


def test_doctor_no_project_valid_hub_warns_only(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    hub = _project(tmp_path / "hub")
    monkeypatch.setattr(Path, "home", lambda: home)
    _write_home_hub(home, hub, monkeypatch)

    report = build_doctor_report(start=tmp_path / "empty")

    assert report.status == "warning"
    assert any(check.id == "project.found" and check.status == "warning" for check in report.checks)
    assert any(check.id == "hub.valid" and check.status == "ok" for check in report.checks)


def test_doctor_tool_specific_missing_hook_errors(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    monkeypatch.setattr(Path, "home", lambda: home)

    for tool, check_id in (
        ("claude", "hook.claude"),
        ("cursor", "hook.cursor"),
        ("gemini", "hook.gemini"),
    ):
        report = build_doctor_report(start=project, tool=tool)  # type: ignore[arg-type]
        assert report.status == "error"
        assert any(check.id == check_id and check.status == "error" for check in report.checks)


def test_doctor_unattributed_and_quarantine_warnings(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    state = home / ".halyard"
    state.mkdir(parents=True)
    (state / "unattributed.log").write_text(
        _session(end=datetime.now()).to_log_line() + "\n", encoding="utf-8"
    )
    (state / "quarantine.log").write_text("; error=bad\nnot a session\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: home)

    report = build_doctor_report(start=project)

    assert any(
        check.id == "state.unattributed" and check.status == "warning" for check in report.checks
    )
    assert any(
        check.id == "state.quarantine" and check.status == "warning" for check in report.checks
    )


def test_doctor_integrity_uses_project_mode(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from halyard import state_integrity

    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    (project / "halyard.toml").write_text('state_integrity = "hash"\n', encoding="utf-8")
    active = home / ".halyard" / "active"
    write_trusted_state(
        active,
        f"slug=acme:auth\ntimeclock={project / 'time.timeclock'}\nstarted=2026-05-22T12:00:00\n",
        mode="hash",
    )
    monkeypatch.setattr(Path, "home", lambda: home)
    state_integrity._reset_cache_for_tests()

    report = build_doctor_report(start=project)
    integrity = next(check for check in report.checks if check.id == "state.integrity")

    assert integrity.status == "ok"
    assert integrity.detail.startswith("mode=hash")


def test_doctor_first_capture_recent_project_session(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 5, 8, 12, 0)
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    (project / AI_LOG_FILENAME).write_text(_session(end=now).to_log_line() + "\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: home)

    report = build_doctor_report(start=project, first_capture=True, now=now)

    assert any(
        check.id == "first_capture.recent" and check.status == "ok" for check in report.checks
    )


def test_doctor_first_capture_unattributed_warning(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 5, 8, 12, 0)
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    state = home / ".halyard"
    state.mkdir(parents=True)
    (state / "unattributed.log").write_text(
        _session(end=now, project=None).to_log_line() + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(Path, "home", lambda: home)

    report = build_doctor_report(start=project, first_capture=True, now=now)

    assert any(
        check.id == "first_capture.unattributed" and check.status == "warning"
        for check in report.checks
    )


def test_doctor_first_capture_missing_errors(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 5, 8, 12, 0)
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    monkeypatch.setattr(Path, "home", lambda: home)

    report = build_doctor_report(start=project, first_capture=True, now=now)

    assert any(
        check.id == "first_capture.missing" and check.status == "error" for check in report.checks
    )


def test_doctor_json_schema(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    monkeypatch.setattr(Path, "home", lambda: home)

    report = build_doctor_report(start=project)
    data = json.loads(render_json(report))

    assert "status" in data
    assert "checks" in data
    assert {"id", "label", "status", "detail", "fix"} <= set(data["checks"][0])


def test_doctor_cli_json_exit_code(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    result = CliRunner().invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "warning"


def test_doctor_cli_invalid_tool_exits_1() -> None:
    result = CliRunner().invoke(app, ["doctor", "--tool", "invalid-ai-tool"])

    assert result.exit_code == 1
    assert "--tool must be one of" in result.stdout


# ---------------------------------------------------------------------------
# v2.31: Duplicate hook detection
# ---------------------------------------------------------------------------


def _hook_settings_content() -> str:
    return json.dumps(
        {
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "/bin/halyard cc-session"}]}
                ],
                "Stop": [{"hooks": [{"type": "command", "command": "/bin/halyard cc-hook"}]}],
            }
        }
    )


def test_duplicate_check_warns_when_hooks_in_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(_hook_settings_content(), encoding="utf-8")
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(_hook_settings_content(), encoding="utf-8")

    result = _claude_hook_duplicate_check(project)

    assert result is not None
    assert result.status == "warning"
    assert result.id == "hook.claude.duplicate"


def test_duplicate_check_clean_when_only_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(_hook_settings_content(), encoding="utf-8")

    result = _claude_hook_duplicate_check(project)

    assert result is None


def test_duplicate_check_clean_when_neither_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    result = _claude_hook_duplicate_check(project)

    assert result is None
