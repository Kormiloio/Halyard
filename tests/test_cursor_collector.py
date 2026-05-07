"""Tests for the Cursor hook collector."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.collectors.cursor import handle_stop_hook, record_session_start

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_stdin(payload: dict) -> patch:  # type: ignore[type-arg]
    return patch("halyard.collectors.cursor.sys.stdin.read", return_value=json.dumps(payload))


def _stop_payload(
    model: str = "claude-3.5-sonnet",
    input_tokens: int = 2000,
    output_tokens: int = 400,
    workspace_roots: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    return {
        "hook_event_name": "stop",
        "model": model,
        "workspace_roots": workspace_roots or [],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }


def _halyard_project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "halyard.toml").write_text("[project]\nslug = 'test'\n")
    (tmp_path / "ai-sessions.log").write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# record_session_start
# ---------------------------------------------------------------------------


def test_record_session_start_creates_state_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "cursor-session"
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)

    result = record_session_start()

    assert result == 0
    assert state_file.exists()
    # Should contain a parseable ISO timestamp
    ts = datetime.fromisoformat(state_file.read_text().strip())
    assert ts.year == datetime.now().year


def test_record_session_start_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "cursor-session"
    state_file.write_text("2026-05-07T10:00:00")
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)

    record_session_start()

    # Should not overwrite existing timestamp
    assert state_file.read_text().strip() == "2026-05-07T10:00:00"


# ---------------------------------------------------------------------------
# handle_stop_hook
# ---------------------------------------------------------------------------


def test_handle_stop_hook_writes_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cursor-session"
    state_file.write_text("2026-05-07T10:00:00")
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor._read_active_project", lambda: "acme:web")

    payload = _stop_payload(workspace_roots=[str(project)])
    with _patch_stdin(payload):
        result = handle_stop_hook()

    assert result == 0
    log_text = (project / "ai-sessions.log").read_text()
    data_lines = [ln for ln in log_text.splitlines() if ln.startswith("s ")]
    assert len(data_lines) == 1
    parts = data_lines[0].split()
    assert parts[3] == "cursor"
    assert parts[4] == "claude-3.5-sonnet"
    assert parts[5] == "2000"
    assert parts[6] == "400"
    assert "project=acme:web" in data_lines[0]
    assert "billing=credits" in data_lines[0]


def test_handle_stop_hook_clears_state_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cursor-session"
    state_file.write_text("2026-05-07T10:00:00")
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor._read_active_project", lambda: None)

    with _patch_stdin(_stop_payload(workspace_roots=[str(project)])):
        handle_stop_hook()

    assert not state_file.exists()


def test_handle_stop_hook_uses_workspace_root_for_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Project is not the cwd — discovered via workspace_roots
    project = _halyard_project(tmp_path / "deep" / "workspace")
    state_file = tmp_path / "cursor-session"
    state_file.write_text("2026-05-07T10:00:00")
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor._read_active_project", lambda: None)

    with _patch_stdin(_stop_payload(workspace_roots=[str(project)])):
        handle_stop_hook()

    data_lines = [
        ln for ln in (project / "ai-sessions.log").read_text().splitlines() if ln.startswith("s ")
    ]
    assert len(data_lines) == 1


def test_handle_stop_hook_skips_when_no_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "cursor-session"
    state_file.write_text("2026-05-07T10:00:00")
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)

    with _patch_stdin(_stop_payload(workspace_roots=["/nonexistent/path"])):
        result = handle_stop_hook()

    assert result == 0
    # State file should still be cleared
    assert not state_file.exists()


def test_handle_stop_hook_uses_now_when_no_start_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cursor-session-missing"
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor._read_active_project", lambda: None)

    with _patch_stdin(_stop_payload(workspace_roots=[str(project)])):
        handle_stop_hook()

    data_lines = [
        ln for ln in (project / "ai-sessions.log").read_text().splitlines() if ln.startswith("s ")
    ]
    assert len(data_lines) == 1


def test_handle_stop_hook_cache_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cursor-session"
    state_file.write_text("2026-05-07T10:00:00")
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor._read_active_project", lambda: None)

    payload = {
        "model": "claude-3.5-sonnet",
        "workspace_roots": [str(project)],
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 500,
            "cache_creation_input_tokens": 100,
        },
    }
    with _patch_stdin(payload):
        handle_stop_hook()

    data_lines = [
        ln for ln in (project / "ai-sessions.log").read_text().splitlines() if ln.startswith("s ")
    ]
    assert "cache_read=500" in data_lines[0]
    assert "cache_write=100" in data_lines[0]


def test_handle_stop_hook_tokens_available_false_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cursor-session"
    state_file.write_text("2026-05-07T10:00:00")
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor._read_active_project", lambda: None)

    payload = {"model": "cursor-unknown", "workspace_roots": [str(project)], "usage": {}}
    with _patch_stdin(payload):
        handle_stop_hook()

    from halyard.ai_log import parse_sessions

    sessions = parse_sessions(project)
    assert len(sessions) == 1
    assert sessions[0].tokens_available is False


# ---------------------------------------------------------------------------
# install-cursor-hook CLI integration
# ---------------------------------------------------------------------------


def test_install_cursor_hook_writes_hooks_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "halyard.cli.Path.home",
        lambda: tmp_path,  # type: ignore[attr-defined]
    )

    from typer.testing import CliRunner

    from halyard.cli import app

    (tmp_path / ".cursor").mkdir()
    runner = CliRunner()
    runner.invoke(app, ["install-cursor-hook"])
    cursor_hooks = tmp_path / ".cursor" / "hooks.json"
    if cursor_hooks.exists():
        data = json.loads(cursor_hooks.read_text())
        assert "beforeSubmitPrompt" in data["hooks"]
        assert "stop" in data["hooks"]
