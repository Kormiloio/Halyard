"""Tests for v2.24 outcome metadata captured by collectors.

Verifies that branch, commit_count, code_added, code_removed are written
into the session log by each collector's handle_stop_hook / import path.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.ai_log import parse_sessions

_RECENT_START = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _halyard_project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "halyard.toml").write_text("[project]\nslug = 'test'\n")
    (tmp_path / "ai-sessions.log").write_text("; Halyard AI session log\n")
    return tmp_path


def _patch_cc_stdin(payload: dict) -> patch:  # type: ignore[type-arg]
    return patch("halyard.collectors.claude_code.sys.stdin.read", return_value=json.dumps(payload))


def _stop_payload_cc(
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 1000,
    output_tokens: int = 200,
) -> dict:  # type: ignore[type-arg]
    return {
        "hook_event_name": "stop",
        "model": model,
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0,
        },
    }


# ---------------------------------------------------------------------------
# Claude Code collector — branch field
# ---------------------------------------------------------------------------


def test_cc_stop_captures_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cc-session"
    state_file.write_text(json.dumps({"start": _RECENT_START, "sha_at_start": None}))
    monkeypatch.setattr("halyard.collectors.claude_code._CC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.claude_code.find_project_dir", lambda **_kw: project)
    monkeypatch.setattr("halyard.collectors.claude_code.current_branch", lambda _: "feature/auth")
    monkeypatch.setattr("halyard.collectors.claude_code.commits_in_window", lambda *_a, **_k: 3)
    monkeypatch.setattr("halyard.collectors.claude_code.numstat_delta", lambda *_a: None)

    from halyard.collectors.claude_code import handle_stop_hook

    with _patch_cc_stdin(_stop_payload_cc()):
        handle_stop_hook()

    sessions = parse_sessions(project)
    assert len(sessions) == 1
    assert sessions[0].branch == "feature/auth"


def test_cc_stop_captures_commit_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cc-session"
    state_file.write_text(json.dumps({"start": _RECENT_START, "sha_at_start": None}))
    monkeypatch.setattr("halyard.collectors.claude_code._CC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.claude_code.find_project_dir", lambda **_kw: project)
    monkeypatch.setattr("halyard.collectors.claude_code.current_branch", lambda _: "main")
    monkeypatch.setattr("halyard.collectors.claude_code.commits_in_window", lambda *_a, **_k: 7)
    monkeypatch.setattr("halyard.collectors.claude_code.numstat_delta", lambda *_a: None)

    from halyard.collectors.claude_code import handle_stop_hook

    with _patch_cc_stdin(_stop_payload_cc()):
        handle_stop_hook()

    sessions = parse_sessions(project)
    assert sessions[0].commit_count == 7


def test_cc_stop_captures_code_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cc-session"
    state_file.write_text(json.dumps({"start": _RECENT_START, "sha_at_start": "abc123"}))
    monkeypatch.setattr("halyard.collectors.claude_code._CC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.claude_code.find_project_dir", lambda **_kw: project)
    monkeypatch.setattr("halyard.collectors.claude_code.current_branch", lambda _: "main")
    monkeypatch.setattr("halyard.collectors.claude_code.commits_in_window", lambda *_a, **_k: 2)
    monkeypatch.setattr("halyard.collectors.claude_code.numstat_delta", lambda *_a: (150, 40))

    from halyard.collectors.claude_code import handle_stop_hook

    with _patch_cc_stdin(_stop_payload_cc()):
        handle_stop_hook()

    sessions = parse_sessions(project)
    assert sessions[0].code_added == 150
    assert sessions[0].code_removed == 40


def test_cc_stop_no_delta_when_no_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cc-session"
    # sha_at_start is None — numstat should not be called
    state_file.write_text(json.dumps({"start": _RECENT_START, "sha_at_start": None}))
    monkeypatch.setattr("halyard.collectors.claude_code._CC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.claude_code.find_project_dir", lambda **_kw: project)
    monkeypatch.setattr("halyard.collectors.claude_code.current_branch", lambda _: "main")
    monkeypatch.setattr("halyard.collectors.claude_code.commits_in_window", lambda *_a, **_k: 0)

    numstat_called = []

    def _numstat_spy(*_a: object) -> None:
        numstat_called.append(True)
        return None

    monkeypatch.setattr("halyard.collectors.claude_code.numstat_delta", _numstat_spy)

    from halyard.collectors.claude_code import handle_stop_hook

    with _patch_cc_stdin(_stop_payload_cc()):
        handle_stop_hook()

    assert not numstat_called
    sessions = parse_sessions(project)
    assert sessions[0].code_added is None
    assert sessions[0].code_removed is None


# ---------------------------------------------------------------------------
# Cursor collector — branch + commit_count
# ---------------------------------------------------------------------------


def _patch_cursor_stdin(payload: dict) -> patch:  # type: ignore[type-arg]
    return patch("halyard.collectors.cursor.sys.stdin.read", return_value=json.dumps(payload))


def _stop_payload_cursor(
    model: str = "claude-3.5-sonnet",
    workspace_roots: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    return {
        "hook_event_name": "stop",
        "model": model,
        "workspace_roots": workspace_roots or [],
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }


def test_cursor_stop_captures_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cursor-session"
    state_file.write_text(json.dumps({"start": _RECENT_START, "sha_at_start": None}))
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor.read_active_project", lambda: None)
    monkeypatch.setattr("halyard.collectors.cursor.current_branch", lambda _: "fix/login")
    monkeypatch.setattr("halyard.collectors.cursor.commits_in_window", lambda *_a, **_k: 1)
    monkeypatch.setattr("halyard.collectors.cursor.numstat_delta", lambda *_a: None)

    from halyard.collectors.cursor import handle_stop_hook

    with _patch_cursor_stdin(_stop_payload_cursor(workspace_roots=[str(project)])):
        handle_stop_hook()

    sessions = parse_sessions(project)
    assert len(sessions) == 1
    assert sessions[0].branch == "fix/login"


def test_cursor_stop_captures_commit_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cursor-session"
    state_file.write_text(json.dumps({"start": _RECENT_START, "sha_at_start": None}))
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor.read_active_project", lambda: None)
    monkeypatch.setattr("halyard.collectors.cursor.current_branch", lambda _: "main")
    monkeypatch.setattr("halyard.collectors.cursor.commits_in_window", lambda *_a, **_k: 5)
    monkeypatch.setattr("halyard.collectors.cursor.numstat_delta", lambda *_a: None)

    from halyard.collectors.cursor import handle_stop_hook

    with _patch_cursor_stdin(_stop_payload_cursor(workspace_roots=[str(project)])):
        handle_stop_hook()

    sessions = parse_sessions(project)
    assert sessions[0].commit_count == 5


def test_cursor_stop_captures_code_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "cursor-session"
    state_file.write_text(json.dumps({"start": _RECENT_START, "sha_at_start": "deadbeef"}))
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor.read_active_project", lambda: None)
    monkeypatch.setattr("halyard.collectors.cursor.current_branch", lambda _: "main")
    monkeypatch.setattr("halyard.collectors.cursor.commits_in_window", lambda *_a, **_k: 2)
    monkeypatch.setattr("halyard.collectors.cursor.numstat_delta", lambda *_a: (80, 20))

    from halyard.collectors.cursor import handle_stop_hook

    with _patch_cursor_stdin(_stop_payload_cursor(workspace_roots=[str(project)])):
        handle_stop_hook()

    sessions = parse_sessions(project)
    assert sessions[0].code_added == 80
    assert sessions[0].code_removed == 20


# ---------------------------------------------------------------------------
# Gemini collector — branch + commit_count (no sha_at_start)
# ---------------------------------------------------------------------------


def _gemini_hook_state(project: Path) -> str:
    recent = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
    return json.dumps(
        {
            "turn_start": recent,
            "cwd": str(project),
            "model": "gemini-2.5-pro",
            "session_id": "test-session-001",
            "prompt_tokens": 500,
            "output_tokens": 100,
            "cache_tokens": 0,
        }
    )


def _gemini_stop_payload(cwd: str) -> str:
    return json.dumps(
        {
            "hook_event_name": "AfterAgent",
            "cwd": cwd,
            "prompt": "hello",
            "stop_hook_active": False,
        }
    )


def test_gemini_stop_captures_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "gc-session"
    state_file.write_text(_gemini_hook_state(project))

    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.gemini_cli.read_active_project", lambda: None)
    monkeypatch.setattr("halyard.collectors.gemini_cli.current_branch", lambda _: "feat/gemini")
    monkeypatch.setattr("halyard.collectors.gemini_cli.commits_in_window", lambda *_a, **_k: 2)

    from unittest.mock import patch as _patch

    from halyard.collectors.gemini_cli import handle_agent_stop

    with _patch(
        "halyard.collectors.gemini_cli.sys.stdin.read",
        return_value=_gemini_stop_payload(str(project)),
    ):
        handle_agent_stop()

    sessions = parse_sessions(project)
    assert len(sessions) == 1
    assert sessions[0].branch == "feat/gemini"


def test_gemini_stop_captures_commit_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "gc-session"
    state_file.write_text(_gemini_hook_state(project))

    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.gemini_cli.read_active_project", lambda: None)
    monkeypatch.setattr("halyard.collectors.gemini_cli.current_branch", lambda _: "main")
    monkeypatch.setattr("halyard.collectors.gemini_cli.commits_in_window", lambda *_a, **_k: 9)

    from unittest.mock import patch as _patch

    from halyard.collectors.gemini_cli import handle_agent_stop

    with _patch(
        "halyard.collectors.gemini_cli.sys.stdin.read",
        return_value=_gemini_stop_payload(str(project)),
    ):
        handle_agent_stop()

    sessions = parse_sessions(project)
    assert sessions[0].commit_count == 9
