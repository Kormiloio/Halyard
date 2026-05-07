"""Tests for the Gemini CLI hook collector."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.collectors.gemini_cli import (
    handle_agent_stop,
    record_model_usage,
    record_session_start,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_stdin(payload: dict) -> patch:  # type: ignore[type-arg]
    return patch("halyard.collectors.gemini_cli.sys.stdin.read", return_value=json.dumps(payload))


def _session_start_payload(
    session_id: str = "sess-1",
    cwd: str = "/some/project",
    timestamp: str = "2026-05-07T10:00:00",
) -> dict:  # type: ignore[type-arg]
    return {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "SessionStart",
        "timestamp": timestamp,
    }


def _after_model_payload(
    model: str = "gemini-2.0-pro",
    prompt_tokens: int = 1500,
    candidates_tokens: int = 200,
) -> dict:  # type: ignore[type-arg]
    return {
        "hook_event_name": "AfterModel",
        "llm_request": {"model": model},
        "llm_response": {
            "usageMetadata": {
                "promptTokenCount": prompt_tokens,
                "candidatesTokenCount": candidates_tokens,
                "totalTokenCount": prompt_tokens + candidates_tokens,
            }
        },
    }


def _after_agent_payload(cwd: str = "/some/project") -> dict:  # type: ignore[type-arg]
    return {
        "hook_event_name": "AfterAgent",
        "cwd": cwd,
        "prompt": "Hello",
        "prompt_response": "Hi there",
        "stop_hook_active": False,
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


def test_record_session_start_writes_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "gc-session"
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)

    with _patch_stdin(_session_start_payload()):
        result = record_session_start()

    assert result == 0
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["session_id"] == "sess-1"
    assert state["cwd"] == "/some/project"
    assert state["turn_start"] == "2026-05-07T10:00:00"
    assert state["prompt_tokens"] == 0
    assert state["output_tokens"] == 0


def test_record_session_start_resets_counters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "gc-session"
    # Pre-existing state with stale token counts
    state_file.write_text(json.dumps({"prompt_tokens": 999, "output_tokens": 500}))
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)

    with _patch_stdin(_session_start_payload()):
        record_session_start()

    state = json.loads(state_file.read_text())
    assert state["prompt_tokens"] == 0
    assert state["output_tokens"] == 0


# ---------------------------------------------------------------------------
# record_model_usage
# ---------------------------------------------------------------------------


def test_record_model_usage_accumulates_output_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "gc-session"
    state_file.write_text(
        json.dumps(
            {
                "turn_start": "2026-05-07T10:00:00",
                "cwd": "/p",
                "model": "",
                "prompt_tokens": 0,
                "output_tokens": 0,
            }
        )
    )
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)

    # First model call
    with _patch_stdin(_after_model_payload(prompt_tokens=1000, candidates_tokens=100)):
        record_model_usage()

    state = json.loads(state_file.read_text())
    assert state["prompt_tokens"] == 1000
    assert state["output_tokens"] == 100
    assert state["model"] == "gemini-2.0-pro"

    # Second model call — cumulative prompt grows, output accumulates
    with _patch_stdin(_after_model_payload(prompt_tokens=1200, candidates_tokens=150)):
        record_model_usage()

    state = json.loads(state_file.read_text())
    assert state["prompt_tokens"] == 1200  # latest (largest) cumulative
    assert state["output_tokens"] == 250  # 100 + 150


def test_record_model_usage_noop_without_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "gc-session-missing"
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)

    with _patch_stdin(_after_model_payload()):
        result = record_model_usage()

    assert result == 0


# ---------------------------------------------------------------------------
# handle_agent_stop
# ---------------------------------------------------------------------------


def test_handle_agent_stop_writes_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "gc-session"
    state_file.write_text(
        json.dumps(
            {
                "turn_start": "2026-05-07T10:00:00",
                "cwd": str(project),
                "model": "gemini-2.0-pro",
                "prompt_tokens": 1500,
                "output_tokens": 300,
            }
        )
    )
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.gemini_cli._read_active_project", lambda: "acme:web")

    with _patch_stdin(_after_agent_payload(cwd=str(project))):
        result = handle_agent_stop()

    assert result == 0
    log_lines = (project / "ai-sessions.log").read_text().splitlines()
    data_lines = [ln for ln in log_lines if ln.startswith("s ")]
    assert len(data_lines) == 1
    parts = data_lines[0].split()
    assert parts[3] == "gemini-cli"
    assert parts[4] == "gemini-2.0-pro"
    assert parts[5] == "1500"
    assert parts[6] == "300"
    assert "project=acme:web" in data_lines[0]


def test_handle_agent_stop_resets_accumulators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "gc-session"
    state_file.write_text(
        json.dumps(
            {
                "turn_start": "2026-05-07T10:00:00",
                "cwd": str(project),
                "model": "gemini-2.0-pro",
                "prompt_tokens": 1000,
                "output_tokens": 200,
            }
        )
    )
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.gemini_cli._read_active_project", lambda: None)

    with _patch_stdin(_after_agent_payload(cwd=str(project))):
        handle_agent_stop()

    state = json.loads(state_file.read_text())
    assert state["prompt_tokens"] == 0
    assert state["output_tokens"] == 0
    assert state["model"] == ""


def test_handle_agent_stop_skips_when_no_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "gc-session"
    state_file.write_text(
        json.dumps(
            {
                "turn_start": "2026-05-07T10:00:00",
                "cwd": "/nonexistent/random/path",
                "model": "gemini-2.0-pro",
                "prompt_tokens": 100,
                "output_tokens": 50,
            }
        )
    )
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)

    with _patch_stdin(_after_agent_payload(cwd="/nonexistent/random/path")):
        result = handle_agent_stop()

    assert result == 0


def test_handle_agent_stop_tokens_available_false_when_no_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "gc-session"
    state_file.write_text(
        json.dumps(
            {
                "turn_start": "2026-05-07T10:00:00",
                "cwd": str(project),
                "model": "gemini-unknown",
                "prompt_tokens": 0,
                "output_tokens": 0,
            }
        )
    )
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.gemini_cli._read_active_project", lambda: None)

    with _patch_stdin(_after_agent_payload(cwd=str(project))):
        handle_agent_stop()

    from halyard.ai_log import parse_sessions as read_sessions

    sessions = read_sessions(project)
    assert len(sessions) == 1
    assert sessions[0].tokens_available is False


def test_full_turn_sequence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SessionStart → AfterModel x2 → AfterAgent produces one correct record."""
    project = _halyard_project(tmp_path / "project")
    state_file = tmp_path / "gc-session"
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.gemini_cli._read_active_project", lambda: None)

    with _patch_stdin(_session_start_payload(cwd=str(project), timestamp="2026-05-07T10:00:00")):
        record_session_start()

    with _patch_stdin(_after_model_payload(prompt_tokens=1000, candidates_tokens=100)):
        record_model_usage()

    with _patch_stdin(_after_model_payload(prompt_tokens=1200, candidates_tokens=150)):
        record_model_usage()

    with _patch_stdin(_after_agent_payload(cwd=str(project))):
        handle_agent_stop()

    from halyard.ai_log import parse_sessions as read_sessions

    sessions = read_sessions(project)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.input_tokens == 1200
    assert s.output_tokens == 250
    assert s.model == "gemini-2.0-pro"
    assert s.tool == "gemini-cli"
    assert s.billing == "seat"
