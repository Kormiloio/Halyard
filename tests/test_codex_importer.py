"""Tests for the Codex Desktop session importer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from halyard.collectors.codex_app import (
    _extract_uuid,
    _parse_iso,
    _parse_session_file,
    import_codex_sessions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SESSION_UUID = "019dffa9-da47-74d0-bb2e-ed75d577ad58"
_SESSION_FILENAME = f"rollout-2026-05-06T19-40-14-{_SESSION_UUID}.jsonl"


def _make_session_file(
    tmp_path: Path, events: list[dict], filename: str = _SESSION_FILENAME
) -> Path:  # type: ignore[type-arg]
    path = tmp_path / filename
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return path


def _real_session_events(
    cwd: str = "/some/project",
    model: str = "gpt-5.5",
    input_tokens: int = 29776,
    cached_input_tokens: int = 23936,
    output_tokens: int = 220,
) -> list[dict]:  # type: ignore[type-arg]
    return [
        {
            "timestamp": "2026-05-06T19:40:47.921Z",
            "type": "session_meta",
            "payload": {
                "id": _SESSION_UUID,
                "timestamp": "2026-05-06T19:40:14.799Z",
                "cwd": cwd,
                "model_provider": "openai",
            },
        },
        {
            "timestamp": "2026-05-06T19:40:50.000Z",
            "type": "turn_context",
            "payload": {"turn_id": "t1", "cwd": cwd, "model": model},
        },
        {
            "timestamp": "2026-05-06T19:41:02.787Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": cached_input_tokens,
                        "output_tokens": output_tokens,
                    }
                },
            },
        },
    ]


# ---------------------------------------------------------------------------
# _extract_uuid
# ---------------------------------------------------------------------------


def test_extract_uuid_parses_standard_filename() -> None:
    path = Path(f"rollout-2026-05-06T19-40-14-{_SESSION_UUID}.jsonl")
    assert _extract_uuid(path) == _SESSION_UUID


def test_extract_uuid_returns_none_for_non_matching() -> None:
    assert _extract_uuid(Path("other-file.jsonl")) is None


# ---------------------------------------------------------------------------
# _parse_iso
# ---------------------------------------------------------------------------


def test_parse_iso_utc_z() -> None:
    dt = _parse_iso("2026-05-06T19:40:14.799Z")
    # Result must be local-naive (no tzinfo)
    assert dt is not None
    assert dt.tzinfo is None
    # Value must equal the UTC input converted to local time
    expected = (
        datetime.fromisoformat("2026-05-06T19:40:14.799+00:00")
        .astimezone(tz=None)
        .replace(tzinfo=None)
    )
    assert dt == expected


def test_parse_iso_empty_returns_none() -> None:
    assert _parse_iso("") is None


def test_parse_iso_invalid_returns_none() -> None:
    assert _parse_iso("not-a-date") is None


# ---------------------------------------------------------------------------
# _parse_session_file
# ---------------------------------------------------------------------------


def test_parse_real_session_extracts_tokens(tmp_path: Path) -> None:
    path = _make_session_file(tmp_path, _real_session_events())
    result = _parse_session_file(path)

    assert result is not None
    session, cwd = result
    # net input = total - cached
    assert session.input_tokens == 29776 - 23936
    assert session.output_tokens == 220
    assert session.cache_read == 23936
    assert session.cost_usd == 0.0
    assert session.tool == "codex"
    assert session.model == "gpt-5.5"
    assert session.billing == "credits"
    assert session.source == "sdk"
    assert cwd == "/some/project"


def test_parse_session_start_from_session_meta(tmp_path: Path) -> None:
    path = _make_session_file(tmp_path, _real_session_events())
    result = _parse_session_file(path)
    assert result is not None
    session, _ = result
    # Should use session_meta.payload.timestamp, not first event timestamp
    expected = (
        datetime.fromisoformat("2026-05-06T19:40:14.799+00:00")
        .astimezone(tz=None)
        .replace(tzinfo=None)
    )
    assert session.start == expected


def test_parse_session_end_is_last_event_timestamp(tmp_path: Path) -> None:
    path = _make_session_file(tmp_path, _real_session_events())
    result = _parse_session_file(path)
    assert result is not None
    session, _ = result
    expected_end = (
        datetime.fromisoformat("2026-05-06T19:41:02.787+00:00")
        .astimezone(tz=None)
        .replace(tzinfo=None)
    )
    assert session.end == expected_end


def test_parse_skips_zero_output_tokens(tmp_path: Path) -> None:
    events = _real_session_events(output_tokens=0)
    path = _make_session_file(tmp_path, events)
    assert _parse_session_file(path) is None


def test_parse_returns_none_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / _SESSION_FILENAME
    path.write_text("", encoding="utf-8")
    assert _parse_session_file(path) is None


def test_parse_uses_last_token_count_event(tmp_path: Path) -> None:
    # Two token_count events — should use the last (cumulative) one
    events = _real_session_events(input_tokens=10000, cached_input_tokens=0, output_tokens=100)
    events.append(
        {
            "timestamp": "2026-05-06T19:42:00.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 29776,
                        "cached_input_tokens": 23936,
                        "output_tokens": 220,
                    }
                },
            },
        }
    )
    path = _make_session_file(tmp_path, events)
    result = _parse_session_file(path)
    assert result is not None
    session, _ = result
    assert session.output_tokens == 220
    assert session.input_tokens == 29776 - 23936


def test_parse_session_file_records_safe_metadata_counts(tmp_path: Path) -> None:
    events = _real_session_events()
    events.insert(
        2,
        {
            "timestamp": "2026-05-06T19:40:55.000Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "do not log this content"},
        },
    )
    events.insert(
        3,
        {
            "timestamp": "2026-05-06T19:40:56.000Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "do not log this either"},
        },
    )
    events.insert(
        4,
        {
            "timestamp": "2026-05-06T19:40:57.000Z",
            "type": "event_msg",
            "payload": {"type": "exec_command_begin", "cmd": "secret command text"},
        },
    )
    events.insert(
        5,
        {
            "timestamp": "2026-05-06T19:40:58.000Z",
            "type": "event_msg",
            "payload": {"type": "exec_command_end", "exit_code": 1},
        },
    )
    path = _make_session_file(tmp_path, events)
    result = _parse_session_file(path)

    assert result is not None
    session, _ = result
    assert session.user_message_count == 1
    assert session.assistant_message_count == 1
    assert session.prompt_count == 1
    assert session.interaction_count == 2
    assert session.tool_calls == 1
    assert session.tool_errors == 1
    assert session.interaction_data_available is True
    assert session.telemetry_source == "codex-jsonl"
    assert session.telemetry_trust == "observed"
    line = session.to_log_line()
    assert "do not log this content" not in line
    assert "secret command text" not in line


# ---------------------------------------------------------------------------
# import_codex_sessions
# ---------------------------------------------------------------------------


def _halyard_project(tmp_path: Path) -> Path:
    """Create a minimal Halyard project directory."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "halyard.toml").write_text("[project]\nslug = 'test'\n", encoding="utf-8")
    (tmp_path / "ai-sessions.log").write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]\n",
        encoding="utf-8",
    )
    return tmp_path


def test_import_writes_session_to_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    codex_dir = tmp_path / "codex_sessions"
    state_file = tmp_path / "codex-imported"

    session_dir = codex_dir / "2026" / "05" / "06"
    session_dir.mkdir(parents=True)
    _make_session_file(
        session_dir,
        _real_session_events(cwd=str(project)),
        filename=_SESSION_FILENAME,
    )

    # Patch the module-level paths
    import halyard.collectors.codex_app as mod

    monkeypatch.setattr(mod, "_CODEX_SESSIONS_DIR", codex_dir)
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", state_file)

    sessions = import_codex_sessions(project_dir=project)

    assert len(sessions) == 1
    log_lines = (project / "ai-sessions.log").read_text(encoding="utf-8").splitlines()
    data_lines = [ln for ln in log_lines if ln.startswith("s ")]
    assert len(data_lines) == 1
    assert "codex" in data_lines[0]


def test_import_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    codex_dir = tmp_path / "codex_sessions"
    state_file = tmp_path / "codex-imported"

    session_dir = codex_dir / "2026" / "05" / "06"
    session_dir.mkdir(parents=True)
    _make_session_file(
        session_dir,
        _real_session_events(cwd=str(project)),
        filename=_SESSION_FILENAME,
    )

    import halyard.collectors.codex_app as mod

    monkeypatch.setattr(mod, "_CODEX_SESSIONS_DIR", codex_dir)
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", state_file)

    sessions = import_codex_sessions(project_dir=project, dry_run=True)

    assert len(sessions) == 1
    # Nothing written to state file
    assert not state_file.exists()
    log_lines = (project / "ai-sessions.log").read_text(encoding="utf-8").splitlines()
    assert not any(ln.startswith("s ") for ln in log_lines)


def test_import_deduplicates_on_second_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _halyard_project(tmp_path / "project")
    codex_dir = tmp_path / "codex_sessions"
    state_file = tmp_path / "codex-imported"

    session_dir = codex_dir / "2026" / "05" / "06"
    session_dir.mkdir(parents=True)
    _make_session_file(
        session_dir,
        _real_session_events(cwd=str(project)),
        filename=_SESSION_FILENAME,
    )

    import halyard.collectors.codex_app as mod

    monkeypatch.setattr(mod, "_CODEX_SESSIONS_DIR", codex_dir)
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", state_file)

    first = import_codex_sessions(project_dir=project)
    second = import_codex_sessions(project_dir=project)

    assert len(first) == 1
    assert len(second) == 0


def test_import_skips_when_no_codex_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import halyard.collectors.codex_app as mod

    monkeypatch.setattr(mod, "_CODEX_SESSIONS_DIR", tmp_path / "nonexistent")
    sessions = import_codex_sessions(project_dir=tmp_path)
    assert sessions == []


def test_import_skips_when_cwd_not_in_halyard_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No project_dir passed — importer infers from session cwd.
    # cwd doesn't point to a Halyard project, so session is skipped.
    codex_dir = tmp_path / "codex_sessions"
    state_file = tmp_path / "codex-imported"

    session_dir = codex_dir / "2026" / "05" / "06"
    session_dir.mkdir(parents=True)
    _make_session_file(
        session_dir,
        _real_session_events(cwd="/some/random/path"),
        filename=_SESSION_FILENAME,
    )

    import halyard.collectors.codex_app as mod

    monkeypatch.setattr(mod, "_CODEX_SESSIONS_DIR", codex_dir)
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.codex_app.find_hub", lambda: None)

    sessions = import_codex_sessions(project_dir=None)
    assert sessions == []
