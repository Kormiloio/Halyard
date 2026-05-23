"""Tests for v3.6 Windsurf collector."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import parse_sessions
from halyard.collectors.windsurf import finalize_stale_sessions, record_turn


def test_v36_windsurf_session_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # GIVEN a mock home and project
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    (project / "halyard.toml").write_text('[project]\nslug = "acme:auth"\n')
    (project / "ai-sessions.log").write_text("; Halyard\n")

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    tid = "trajectory-123"

    # WHEN recording a start turn
    payload_start = {
        "trajectory_id": tid,
        "model_name": "SWE-1.6 Slow",
        "timestamp": "2026-05-23T10:00:00Z",
    }
    record_turn(payload_start, is_start=True)

    # THEN state file should exist
    state_file = home / ".halyard" / "ws-sessions" / f"{tid}.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["user_count"] == 1
    assert state["assistant_count"] == 0
    assert state["model"] == "SWE-1.6 Slow"

    # WHEN recording a stop turn
    payload_stop = {
        "trajectory_id": tid,
        "timestamp": "2026-05-23T10:01:00Z",
    }
    record_turn(payload_stop, is_start=False)

    # THEN counts should be updated
    state = json.loads(state_file.read_text())
    assert state["user_count"] == 1
    assert state["assistant_count"] == 1

    # WHEN finalizing stale sessions (forcing now to be 31 mins later)
    future_now = datetime.now() + timedelta(minutes=31)

    # We need to monkeypatch datetime.now() in collectors/windsurf.py
    import halyard.collectors.windsurf

    class MockDatetime:
        @classmethod
        def now(cls):
            return future_now

        @classmethod
        def fromisoformat(cls, s):
            return datetime.fromisoformat(s)

    monkeypatch.setattr(halyard.collectors.windsurf, "datetime", MockDatetime)

    finalize_stale_sessions(project_dir=project)

    # THEN state file should be gone and log should have the session
    assert not state_file.exists()
    sessions = parse_sessions(project)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.tool == "windsurf"
    assert s.model == "SWE-1.6_Slow"
    assert s.user_message_count == 1
    assert s.assistant_message_count == 1
    assert s.interaction_count == 2
    assert s.tokens_available is False


def test_v36_windsurf_install_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard.cli_hooks import _do_install_hook_windsurf

    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("halyard.cli_hooks._halyard_exe", lambda: "/usr/local/bin/halyard")

    # WHEN installing the hook
    _do_install_hook_windsurf()

    # THEN hooks.json should be correctly configured
    hooks_file = home / ".codeium" / "windsurf" / "hooks.json"
    assert hooks_file.exists()
    data = json.loads(hooks_file.read_text())

    pre = data["hooks"]["pre_user_prompt"]
    assert any("halyard windsurf-session-start" in h["command"] for h in pre)
    assert pre[0]["show_output"] is False

    post = data["hooks"]["post_cascade_response"]
    assert any("halyard windsurf-session-stop" in h["command"] for h in post)
    assert post[0]["show_output"] is False
