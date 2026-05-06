"""Tests for the Claude Code hook collector and install-hook command."""

from __future__ import annotations

import json
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, parse_sessions
from halyard.cli import app
from halyard.collectors.claude_code import handle_stop_hook, record_session_start

runner = CliRunner()

CC_SESSION_FILE = Path.home() / ".halyard" / "cc-session"
HALYARD_ACTIVE = Path.home() / ".halyard" / "active"


@pytest.fixture(autouse=True)
def clean_state() -> None:  # type: ignore[misc]
    CC_SESSION_FILE.unlink(missing_ok=True)
    HALYARD_ACTIVE.unlink(missing_ok=True)
    yield  # type: ignore[misc]
    CC_SESSION_FILE.unlink(missing_ok=True)
    HALYARD_ACTIVE.unlink(missing_ok=True)


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\nname='Test'\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


# ---------------------------------------------------------------------------
# cc-session (UserPromptSubmit hook)
# ---------------------------------------------------------------------------


def test_cc_session_writes_start_file() -> None:
    record_session_start()
    assert CC_SESSION_FILE.exists()
    ts = datetime.fromisoformat(CC_SESSION_FILE.read_text().strip())
    assert isinstance(ts, datetime)


def test_cc_session_does_not_overwrite_existing() -> None:
    CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CC_SESSION_FILE.write_text("2026-05-06T09:00:00")
    record_session_start()
    assert CC_SESSION_FILE.read_text().strip() == "2026-05-06T09:00:00"


# ---------------------------------------------------------------------------
# cc-hook (Stop hook)
# ---------------------------------------------------------------------------


def _run_stop_hook(tmp_path: Path, payload: dict) -> int:  # type: ignore[type-arg]
    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=tmp_path),
        patch("sys.stdin", StringIO(json.dumps(payload))),
    ):
        return handle_stop_hook()


def test_stop_hook_writes_session_record(tmp_path: Path) -> None:
    _init_project(tmp_path)
    CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CC_SESSION_FILE.write_text("2026-05-06T10:00:00")

    payload = {
        "model": "claude-sonnet-4-6",
        "usage": {"input_tokens": 5000, "output_tokens": 1200},
    }
    rc = _run_stop_hook(tmp_path, payload)

    assert rc == 0
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.tool == "claude-code"
    assert s.model == "claude-sonnet-4-6"
    assert s.input_tokens == 5000
    assert s.output_tokens == 1200
    assert s.tokens_available is True
    assert s.source == "hook"


def test_stop_hook_clears_session_file(tmp_path: Path) -> None:
    _init_project(tmp_path)
    CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CC_SESSION_FILE.write_text("2026-05-06T10:00:00")

    _run_stop_hook(tmp_path, {"model": "claude-sonnet-4-6", "usage": {}})

    assert not CC_SESSION_FILE.exists()


def test_stop_hook_handles_missing_usage(tmp_path: Path) -> None:
    _init_project(tmp_path)
    rc = _run_stop_hook(tmp_path, {"model": "claude-sonnet-4-6"})

    assert rc == 0
    s = parse_sessions(tmp_path)[0]
    assert s.input_tokens == 0
    assert s.output_tokens == 0
    assert s.tokens_available is False


def test_stop_hook_handles_empty_payload(tmp_path: Path) -> None:
    _init_project(tmp_path)
    rc = _run_stop_hook(tmp_path, {})

    assert rc == 0
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].model == "claude-unknown"


def test_stop_hook_silent_when_not_in_halyard_project(tmp_path: Path) -> None:
    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=None),
        patch("sys.stdin", StringIO("{}")),
    ):
        rc = handle_stop_hook()
    assert rc == 0


def test_stop_hook_picks_up_active_project(tmp_path: Path) -> None:
    _init_project(tmp_path)
    HALYARD_ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    HALYARD_ACTIVE.write_text(f"timeclock={tmp_path}/time.timeclock\nslug=acme:auth\nstarted=2026-05-06 10:00:00\n")

    _run_stop_hook(tmp_path, {"model": "claude-opus-4-7", "usage": {"input_tokens": 1000, "output_tokens": 200}})

    s = parse_sessions(tmp_path)[0]
    assert s.project == "acme:auth"


def test_stop_hook_captures_cache_tokens(tmp_path: Path) -> None:
    _init_project(tmp_path)
    payload = {
        "model": "claude-opus-4-7",
        "usage": {
            "input_tokens": 10000,
            "output_tokens": 2000,
            "cache_read_input_tokens": 8000,
            "cache_creation_input_tokens": 2000,
        },
    }
    _run_stop_hook(tmp_path, payload)
    s = parse_sessions(tmp_path)[0]
    assert s.cache_read == 8000
    assert s.cache_write == 2000


# ---------------------------------------------------------------------------
# install-hook
# ---------------------------------------------------------------------------


def test_install_hook_creates_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["install-hook"])

    assert result.exit_code == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "Stop" in settings["hooks"]
    assert "UserPromptSubmit" in settings["hooks"]


def test_install_hook_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["install-hook"])
    runner.invoke(app, ["install-hook"])

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["Stop"]) == 1


def test_install_hook_preserves_existing_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({"model": "claude-opus-4-7"}))

    runner.invoke(app, ["install-hook"])

    settings = json.loads((settings_dir / "settings.json").read_text())
    assert settings["model"] == "claude-opus-4-7"
    assert "hooks" in settings
