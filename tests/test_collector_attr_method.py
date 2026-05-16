"""Gap 5: Attribution cascade priority across collectors.

Priority chain (highest → lowest):
  timer (active project via halyard start) > ws_root (Cursor workspace root) > git

Tests verify that attr_method on the written AiSession reflects the winning
attribution source, not a lower-priority one that also resolved.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.ai_log import AI_LOG_FILENAME, parse_sessions

_RECENT_START = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _halyard_project(tmp_path: Path, slug: str = "test:proj") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "halyard.toml").write_text(f"[project]\nslug = '{slug}'\n")
    (tmp_path / AI_LOG_FILENAME).write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>\n"
    )
    return tmp_path


def _cursor_stop_payload(workspace_root: str) -> str:
    return json.dumps(
        {
            "model": "claude-4-sonnet",
            "cursor_version": "1.0.0",
            "workspace_roots": [workspace_root],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    )


def _cc_stop_payload() -> str:
    return json.dumps(
        {
            "model": "claude-sonnet-4-5",
            "usage": {"input_tokens": 200, "output_tokens": 80},
        }
    )


# ---------------------------------------------------------------------------
# Gap 5a: timer takes precedence over ws_root
# ---------------------------------------------------------------------------


def test_timer_takes_precedence_over_ws_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When active timer AND workspace_root both resolve a project, attr_method=timer."""
    project = _halyard_project(tmp_path / "project", slug="acme:web")
    session_file = tmp_path / "cursor-session"
    session_file.write_text(_RECENT_START)

    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", session_file)
    # Timer is active → read_active_project returns a slug
    monkeypatch.setattr("halyard.collectors.cursor.read_active_project", lambda: "acme:web")
    # ws_root would also resolve the project if given the chance
    monkeypatch.setattr(
        "halyard.collectors.cursor.infer_project",
        lambda _cwd: "acme:web",
    )
    monkeypatch.setattr(
        "halyard.collectors.cursor.find_project_dir",
        lambda **_kw: project,
    )
    monkeypatch.setattr("halyard.collectors.cursor.find_hub", lambda: None)
    monkeypatch.setattr("halyard.collectors.cursor.current_branch", lambda _: None)

    payload = _cursor_stop_payload(str(project))
    with patch("halyard.collectors.cursor.sys.stdin.read", return_value=payload):
        from halyard.collectors.cursor import handle_stop_hook

        handle_stop_hook()

    sessions = parse_sessions(project)
    assert len(sessions) == 1
    assert sessions[0].attr_method == "timer"


# ---------------------------------------------------------------------------
# Gap 5b: timer takes precedence over git
# ---------------------------------------------------------------------------


def test_timer_takes_precedence_over_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When active timer AND git both resolve a project, attr_method=timer."""
    project = _halyard_project(tmp_path / "project", slug="globex:api")
    session_file = tmp_path / "cc-session"
    session_file.write_text(_RECENT_START)

    monkeypatch.setattr("halyard.collectors.claude_code._CC_SESSION_FILE", session_file)
    # Timer active
    monkeypatch.setattr("halyard.collectors.claude_code.read_active_project", lambda: "globex:api")
    # git would also resolve if asked, but timer wins
    monkeypatch.setattr(
        "halyard.collectors.claude_code.infer_project",
        lambda _cwd: "globex:api",
    )
    monkeypatch.setattr(
        "halyard.collectors.claude_code.find_project_dir",
        lambda **_kw: project,
    )
    monkeypatch.setattr("halyard.collectors.claude_code.find_hub", lambda: None)
    monkeypatch.setattr("halyard.collectors.claude_code.current_branch", lambda _: None)

    payload = _cc_stop_payload()
    with patch("halyard.collectors.claude_code.sys.stdin.read", return_value=payload):
        from halyard.collectors.claude_code import handle_stop_hook

        handle_stop_hook()

    sessions = parse_sessions(project)
    assert len(sessions) == 1
    assert sessions[0].attr_method == "timer"


# ---------------------------------------------------------------------------
# Gap 5c: ws_root takes precedence over git
# ---------------------------------------------------------------------------


def test_ws_root_takes_precedence_over_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no active timer but workspace_root resolves a project, attr_method=ws_root (not git)."""
    project = _halyard_project(tmp_path / "project", slug="vcti:site")
    session_file = tmp_path / "cursor-session"
    session_file.write_text(_RECENT_START)

    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", session_file)
    # No active timer
    monkeypatch.setattr("halyard.collectors.cursor.read_active_project", lambda: None)
    # Workspace root resolves the project via git inference
    monkeypatch.setattr(
        "halyard.collectors.cursor.infer_project",
        lambda _cwd: "vcti:site",
    )
    monkeypatch.setattr(
        "halyard.collectors.cursor.find_project_dir",
        lambda **_kw: project,
    )
    monkeypatch.setattr("halyard.collectors.cursor.find_hub", lambda: None)
    monkeypatch.setattr("halyard.collectors.cursor.current_branch", lambda _: None)

    payload = _cursor_stop_payload(str(project))
    with patch("halyard.collectors.cursor.sys.stdin.read", return_value=payload):
        from halyard.collectors.cursor import handle_stop_hook

        handle_stop_hook()

    sessions = parse_sessions(project)
    assert len(sessions) == 1
    # Cursor with a workspace_root that resolved → ws_root, not git
    assert sessions[0].attr_method == "ws_root"
