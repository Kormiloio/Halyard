"""Tests for ai_log.py — AiSession serialization, parsing, and project discovery."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from halyard.ai_log import (
    AI_LOG_FILENAME,
    HEADER,
    AiSession,
    append_session,
    assign_unattributed_sessions,
    find_project_dir,
    parse_sessions,
    write_unattributed_session,
)

START = datetime(2026, 5, 6, 10, 30, 0)
END = datetime(2026, 5, 6, 11, 15, 0)


def _session(**kwargs) -> AiSession:  # type: ignore[no-untyped-def]
    defaults = {
        "start": START,
        "end": END,
        "tool": "claude-code",
        "model": "claude-sonnet-4-6",
        "input_tokens": 10000,
        "output_tokens": 2000,
        "cost_usd": 0.0600,
    }
    defaults.update(kwargs)
    return AiSession(**defaults)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_to_log_line_positional_fields() -> None:
    line = _session().to_log_line()
    parts = line.split()
    assert parts[0] == "s"
    assert parts[1] == "2026-05-06T10:30:00"
    assert parts[2] == "2026-05-06T11:15:00"
    assert parts[3] == "claude-code"
    assert parts[4] == "claude-sonnet-4-6"
    assert parts[5] == "10000"
    assert parts[6] == "2000"
    assert parts[7] == "0.0600"


def test_to_log_line_cost_four_decimal_places() -> None:
    line = _session(cost_usd=1.5).to_log_line()
    assert "1.5000" in line


def test_to_log_line_optional_project() -> None:
    line = _session(project="acme:auth-migration").to_log_line()
    assert "project=acme:auth-migration" in line


def test_to_log_line_omits_default_billing() -> None:
    line = _session(billing="api").to_log_line()
    assert "billing=" not in line


def test_to_log_line_includes_non_default_billing() -> None:
    line = _session(billing="seat").to_log_line()
    assert "billing=seat" in line


def test_to_log_line_tokens_available_false() -> None:
    line = _session(tokens_available=False).to_log_line()
    assert "tokens_available=false" in line


def test_to_log_line_omits_tokens_available_when_true() -> None:
    line = _session(tokens_available=True).to_log_line()
    assert "tokens_available" not in line


def test_to_log_line_note_spaces_become_underscores() -> None:
    line = _session(note="quick check").to_log_line()
    assert "note=quick_check" in line


def test_to_log_line_tags() -> None:
    line = _session(tags=["review", "refactor"]).to_log_line()
    assert "tags=review,refactor" in line


def test_to_log_line_cache_fields() -> None:
    line = _session(cache_read=5000, cache_write=1000).to_log_line()
    assert "cache_read=5000" in line
    assert "cache_write=1000" in line


def test_to_log_line_job_id_and_source() -> None:
    line = _session(job_id="droid-001", source="hook").to_log_line()
    assert "job_id=droid-001" in line
    assert "source=hook" in line


# ---------------------------------------------------------------------------
# Round-trip: write → parse
# ---------------------------------------------------------------------------


def test_round_trip_minimal(tmp_path: Path) -> None:
    s = _session()
    append_session(tmp_path, s)
    parsed = parse_sessions(tmp_path)
    assert len(parsed) == 1
    p = parsed[0]
    assert p.start == s.start
    assert p.end == s.end
    assert p.tool == s.tool
    assert p.model == s.model
    assert p.input_tokens == s.input_tokens
    assert p.output_tokens == s.output_tokens
    assert abs(p.cost_usd - s.cost_usd) < 0.0001


def test_round_trip_all_optional_fields(tmp_path: Path) -> None:
    s = _session(
        project="acme:auth",
        user="mario",
        cache_read=3000,
        cache_write=500,
        tokens_available=False,
        billing="credits",
        credits=12.5,
        job_id="job-abc",
        source="proxy",
        tags=["refactor"],
        note="big refactor",
    )
    append_session(tmp_path, s)
    p = parse_sessions(tmp_path)[0]
    assert p.project == "acme:auth"
    assert p.user == "mario"
    assert p.cache_read == 3000
    assert p.cache_write == 500
    assert p.tokens_available is False
    assert p.billing == "credits"
    assert p.credits == pytest.approx(12.5)
    assert p.job_id == "job-abc"
    assert p.source == "proxy"
    assert p.tags == ["refactor"]
    assert p.note == "big refactor"


def test_parse_ignores_comments_and_blanks(tmp_path: Path) -> None:
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(HEADER + "\n\n; a comment\n")
    assert parse_sessions(tmp_path) == []


def test_parse_ignores_unknown_kv(tmp_path: Path) -> None:
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(
        HEADER + "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-opus-4-7 "
        "5000 1000 0.8250 future_field=xyz\n"
    )
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1


def test_from_log_line_negative_tokens_quarantines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    line = "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-opus-4-7 -1 1000 0.8250"

    assert AiSession.from_log_line(line) is None

    quarantine = tmp_path / ".halyard" / "quarantine.log"
    assert quarantine.exists()
    assert "input_tokens" in quarantine.read_text()


def test_from_log_line_missing_required_field_quarantines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    line = "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code"

    assert AiSession.from_log_line(line) is None

    quarantine = tmp_path / ".halyard" / "quarantine.log"
    assert quarantine.exists()
    assert "expected session line" in quarantine.read_text()


def test_from_log_line_bad_cost_quarantines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    line = "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-opus-4-7 100 50 nope"

    assert AiSession.from_log_line(line) is None

    quarantine = tmp_path / ".halyard" / "quarantine.log"
    assert quarantine.exists()
    assert "invalid cost_usd: nope" in quarantine.read_text()


def test_log_line_error_does_not_write_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    line = "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-opus-4-7 100 bad 0.1234"

    assert AiSession.log_line_error(line) == "invalid output_tokens: bad"
    assert not (tmp_path / ".halyard" / "quarantine.log").exists()


def test_write_unattributed_session_creates_user_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    path = write_unattributed_session(_session(tool="codex"))

    assert path == tmp_path / ".halyard" / "unattributed.log"
    assert "tool" not in path.read_text()
    assert "codex" in path.read_text()


def test_assign_unattributed_sessions_adds_project(tmp_path: Path) -> None:
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(
        HEADER + "s 2026-05-06T10:00:00 2026-05-06T10:30:00 codex codex-local "
        "5000 1000 0.0000 source=codex\n"
    )

    changed = assign_unattributed_sessions(tmp_path, "acme:auth")

    assert changed == 1
    session = parse_sessions(tmp_path)[0]
    assert session.project == "acme:auth"
    assert session.source == "codex"


def test_assign_unattributed_sessions_skips_attributed_records(tmp_path: Path) -> None:
    append_session(tmp_path, _session(project="acme:auth"))

    changed = assign_unattributed_sessions(tmp_path, "globex:reports")

    assert changed == 0
    assert parse_sessions(tmp_path)[0].project == "acme:auth"


def test_append_multiple_sessions(tmp_path: Path) -> None:
    for i in range(3):
        append_session(tmp_path, _session(input_tokens=i * 1000))
    assert len(parse_sessions(tmp_path)) == 3


# ---------------------------------------------------------------------------
# Project discovery
# ---------------------------------------------------------------------------


def test_find_project_dir_finds_halyard_toml(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    assert find_project_dir(tmp_path) == tmp_path


def test_find_project_dir_walks_up(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    subdir = tmp_path / "src" / "deep"
    subdir.mkdir(parents=True)
    assert find_project_dir(subdir) == tmp_path


def test_find_project_dir_returns_none_when_absent(tmp_path: Path) -> None:
    assert find_project_dir(tmp_path) is None


# ---------------------------------------------------------------------------
# Rich session telemetry (v2.6)
# ---------------------------------------------------------------------------


def _base_session(**kwargs) -> AiSession:  # type: ignore[no-untyped-def]
    return AiSession(
        start=datetime(2026, 5, 8, 10, 0, 0),
        end=datetime(2026, 5, 8, 10, 30, 0),
        tool="gemini-cli",
        model="gemini-2.0-flash",
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.0012,
        **kwargs,
    )


def test_rich_fields_round_trip() -> None:
    session = _base_session(
        session_id="abc123def456",
        tool_calls=42,
        tool_errors=3,
        wall_seconds=1800,
        agent_active_seconds=900,
        code_added=150,
        code_removed=40,
        model_breakdown="gemini-2.0-flash:8|gemini-2.0-pro:2",
    )
    line = session.to_log_line()
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.session_id == "abc123def456"
    assert parsed.tool_calls == 42
    assert parsed.tool_errors == 3
    assert parsed.wall_seconds == 1800
    assert parsed.agent_active_seconds == 900
    assert parsed.code_added == 150
    assert parsed.code_removed == 40
    assert parsed.model_breakdown == "gemini-2.0-flash:8|gemini-2.0-pro:2"


def test_rich_fields_absent_on_old_log_line() -> None:
    line = "s 2026-05-08T10:00:00 2026-05-08T10:30:00 gemini-cli gemini-2.0-flash 500 200 0.0012"
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.tool_calls is None
    assert parsed.tool_errors is None
    assert parsed.wall_seconds is None
    assert parsed.session_id is None
    assert parsed.model_breakdown is None


def test_rich_fields_omitted_when_none() -> None:
    session = _base_session()
    line = session.to_log_line()
    assert "tool_calls" not in line
    assert "tool_errors" not in line
    assert "wall_seconds" not in line
    assert "session_id" not in line
    assert "model_breakdown" not in line


def test_malformed_rich_field_ignored() -> None:
    line = "s 2026-05-08T10:00:00 2026-05-08T10:30:00 gemini-cli gemini-2.0-flash 500 200 0.0012 tool_calls=notanint"
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.tool_calls is None


def test_unknown_rich_field_ignored() -> None:
    line = "s 2026-05-08T10:00:00 2026-05-08T10:30:00 gemini-cli gemini-2.0-flash 500 200 0.0012 future_field=somevalue"
    parsed = AiSession.from_log_line(line)
    assert parsed is not None  # must not crash


def test_tool_errors_zero_written_when_calls_known() -> None:
    # tool_errors=0 is meaningful: "5 calls, 0 errors" vs "unknown"
    session = _base_session(tool_calls=5, tool_errors=0)
    line = session.to_log_line()
    assert "tool_calls=5" in line
    assert "tool_errors=0" in line
